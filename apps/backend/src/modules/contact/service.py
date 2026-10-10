from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import CompanyNotFoundError, ContactNotFoundError
from ..company.models import Company
from ..user.models import User
from .models import Contact, Employment, RelationshipHolder
from .schemas import ContactCreate, ContactRead, ContactUpdate, EmploymentRead, HolderRead

CONTACT_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "language",
    "salutation",
    "do_not_contact",
    "marketing_opt_out",
    "legal_basis",
    "source",
)


class ContactService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def get(self, db: AsyncSession, contact_id: int) -> Contact:
        contact = await db.get(Contact, contact_id)
        if contact is None:
            raise ContactNotFoundError(f"Contact {contact_id} not found")
        return contact

    async def _require_company(self, db: AsyncSession, company_id: int) -> None:
        if await db.get(Company, company_id) is None:
            raise CompanyNotFoundError(f"Company {company_id} not found")

    async def _duplicates(self, db: AsyncSession, email: str | None, exclude_id: int | None) -> list[int]:
        if not email:
            return []
        query = select(Contact.id).where(func.lower(Contact.email) == email.lower())
        if exclude_id is not None:
            query = query.where(Contact.id != exclude_id)
        return list((await db.execute(query.order_by(Contact.id))).scalars())

    async def read(self, db: AsyncSession, contact: Contact, duplicates: list[int] | None = None) -> dict[str, Any]:
        roles = (
            await db.execute(
                select(Employment)
                .where(Employment.contact_id == contact.id)
                .order_by(Employment.end_date.is_(None).desc(), Employment.end_date.desc(), Employment.id.desc())
            )
        ).scalars()
        current, history = None, []
        for role in roles:
            item = EmploymentRead.model_validate(role, from_attributes=True)
            if role.end_date is None and current is None:
                current = item
            else:
                history.append(item)
        return ContactRead(
            **{field: getattr(contact, field) for field in CONTACT_FIELDS},
            id=contact.id,
            current_role=current,
            history=history,
            warnings=["duplicate_email"] if duplicates else [],
            duplicate_contact_ids=duplicates or [],
            relationship_holders=(await self.holders(db, [contact.id]))[contact.id],
        ).model_dump(mode="json")

    async def holders(self, db: AsyncSession, contact_ids: list[int]) -> dict[int, list[HolderRead]]:
        """Strongest relationship first."""
        grouped: dict[int, list[HolderRead]] = {contact_id: [] for contact_id in contact_ids}
        if contact_ids:
            rows = await db.execute(
                select(RelationshipHolder, User.name)
                .join(User, User.id == RelationshipHolder.user_id)
                .where(RelationshipHolder.contact_id.in_(contact_ids))
                .order_by(RelationshipHolder.strength.desc(), User.name)
            )
            for holder, name in rows.tuples():
                grouped[holder.contact_id].append(HolderRead(user_id=holder.user_id, name=name, strength=holder.strength))
        return grouped

    async def set_holder(
        self, db: AsyncSession, contact_id: int, user_id: int, strength: int, context: AuditContext
    ) -> dict[str, Any]:
        contact = await self.get(db, contact_id)
        holder = (
            await db.execute(
                select(RelationshipHolder).where(
                    RelationshipHolder.contact_id == contact_id, RelationshipHolder.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        old = {"strength": holder.strength} if holder else None
        if holder is None:
            db.add(RelationshipHolder(contact_id=contact_id, user_id=user_id, strength=strength))
        else:
            holder.strength = strength
        self.audit.record(
            db,
            context,
            "contact.relationship_set",
            record_type="contact",
            record_id=contact_id,
            old_values=old,
            new_values={"user_id": user_id, "strength": strength},
        )
        await db.commit()
        return await self.read(db, contact)

    async def remove_holder(self, db: AsyncSession, contact_id: int, user_id: int, context: AuditContext) -> dict[str, Any]:
        contact = await self.get(db, contact_id)
        holder = (
            await db.execute(
                select(RelationshipHolder).where(
                    RelationshipHolder.contact_id == contact_id, RelationshipHolder.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if holder is not None:
            await db.delete(holder)
            self.audit.record(
                db,
                context,
                "contact.relationship_removed",
                record_type="contact",
                record_id=contact_id,
                old_values={"user_id": user_id, "strength": holder.strength},
            )
            await db.commit()
        return await self.read(db, contact)

    async def create(self, db: AsyncSession, values: ContactCreate, context: AuditContext) -> dict[str, Any]:
        if values.company_id is not None:
            await self._require_company(db, values.company_id)
        duplicates = await self._duplicates(db, values.email, None)
        contact = Contact(**values.model_dump(mode="json", include=set(CONTACT_FIELDS)), owner_id=context.user_id)
        db.add(contact)
        await db.flush()
        if values.company_id is not None:
            db.add(
                Employment(
                    contact_id=contact.id,
                    company_id=values.company_id,
                    function=values.function,
                    start_date=context.clock.now().date(),
                )
            )
        self.audit.record(
            db,
            context,
            "contact.created",
            record_type="contact",
            record_id=contact.id,
            new_values=values.model_dump(mode="json"),
        )
        await db.commit()
        return await self.read(db, contact, duplicates)

    async def update(self, db: AsyncSession, contact_id: int, values: ContactUpdate, context: AuditContext) -> dict[str, Any]:
        contact = await self.get(db, contact_id)
        changes = values.model_dump(mode="json", exclude_unset=True)
        today = context.clock.now().date()
        old = {key: getattr(contact, key) for key in changes if key in CONTACT_FIELDS}

        for key, value in changes.items():
            if key in CONTACT_FIELDS and not (
                value is None and key in ("first_name", "last_name", "source", "marketing_opt_out")
            ):
                setattr(contact, key, value)

        if "company_id" in changes or "function" in changes:
            current = (
                await db.execute(select(Employment).where(Employment.contact_id == contact.id, Employment.end_date.is_(None)))
            ).scalar_one_or_none()
            new_company = changes.get("company_id", current.company_id if current else None)
            if new_company is not None:
                await self._require_company(db, new_company)
            if current is not None and current.company_id == new_company:
                if "function" in changes:
                    current.function = changes["function"]
            else:
                if current is not None:
                    current.end_date = today
                if new_company is not None:
                    db.add(
                        Employment(
                            contact_id=contact.id,
                            company_id=new_company,
                            function=changes.get("function"),
                            start_date=today,
                        )
                    )

        duplicates = await self._duplicates(db, contact.email, contact.id) if "email" in changes else []
        self.audit.record(
            db, context, "contact.updated", record_type="contact", record_id=contact.id, old_values=old, new_values=changes
        )
        await db.commit()
        return await self.read(db, contact, duplicates)

    async def search(self, db: AsyncSession, q: str | None, limit: int) -> list[dict[str, Any]]:
        query = select(Contact).order_by(Contact.last_name, Contact.first_name, Contact.id).limit(limit)
        if q and q.strip():
            term = q.strip()
            query = query.where(
                or_(
                    Contact.first_name.icontains(term, autoescape=True),
                    Contact.last_name.icontains(term, autoescape=True),
                    Contact.email.icontains(term, autoescape=True),
                )
            )
        return [await self.read(db, contact) for contact in (await db.execute(query)).scalars()]

    async def detail(self, db: AsyncSession, contact_id: int) -> dict[str, Any]:
        contact = await self.get(db, contact_id)
        return await self.read(db, contact, await self._duplicates(db, contact.email, contact.id))
