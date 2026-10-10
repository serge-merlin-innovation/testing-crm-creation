from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, String, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationError
from ..company.models import Company
from ..contact.models import Contact, Employment
from ..contact.service import ContactService
from ..mandate.models import Mandate
from ..mandate.policy import DealPolicy
from ..user.models import User
from .models import SavedFilter
from .schemas import MIN_QUERY_LENGTH, SavedFilterCreate, SearchCriteria

FUZZY_THRESHOLD = 0.5


class SavedFilterNotFoundError(ResourceNotFoundError):
    pass


def fold(expression: Any) -> ColumnElement[str]:
    return func.crm_fold(expression)


def matches(expression: Any, term: ColumnElement[str]) -> ColumnElement[bool]:
    """Substring or fuzzy word match, accent- and case-blind; both served by the trigram index."""
    folded = fold(expression)
    return or_(folded.like(func.concat("%", term, "%")), term.op("<%")(folded))


def rank(expression: Any, term: ColumnElement[str]) -> ColumnElement[float]:
    return func.word_similarity(term, fold(expression))


class SearchService:
    def __init__(self, contacts: ContactService | None = None) -> None:
        self.contacts = contacts or ContactService()

    async def search(
        self, db: AsyncSession, user: dict[str, Any], criteria: SearchCriteria, now: datetime, limit: int
    ) -> dict[str, Any]:
        query = (criteria.q or "").strip()
        if len(query) < MIN_QUERY_LENGTH and not criteria.has_criteria():
            raise ValidationError(f"Type at least {MIN_QUERY_LENGTH} characters", field="q")
        term = fold(cast(literal(query), String)) if query else None
        # The default 0.6 misses two-letter typos in a short surname (lefebvre vs lefevre scores 0.55).
        await db.execute(select(func.set_config("pg_trgm.word_similarity_threshold", str(FUZZY_THRESHOLD), True)))
        return {
            "query": query,
            "companies": await self._companies(db, criteria, term, limit),
            "contacts": await self._contacts(db, criteria, term, limit),
            "deals": await self._deals(db, user, criteria, term, now, limit),
        }

    def _company_filters(self, criteria: SearchCriteria) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if criteria.company_types:
            filters.append(Company.type.in_([value.value for value in criteria.company_types]))
        if criteria.country_ids:
            filters.append(Company.country_id.in_(criteria.country_ids))
        if criteria.sector_ids:
            filters.append(Company.sector_id.in_(criteria.sector_ids))
        return filters

    async def _companies(
        self, db: AsyncSession, criteria: SearchCriteria, term: ColumnElement[str] | None, limit: int
    ) -> list[dict[str, Any]]:
        if criteria.ev_min is not None or criteria.ev_max is not None:
            return []
        query = select(Company).where(*self._company_filters(criteria))
        if term is not None:
            query = query.where(matches(Company.name, term)).order_by(rank(Company.name, term).desc(), Company.name)
        else:
            query = query.order_by(Company.name)
        rows = (await db.execute(query.limit(limit))).scalars()
        return [{"id": c.id, "name": c.name, "type": c.type, "country_id": c.country_id} for c in rows]

    async def _contacts(
        self, db: AsyncSession, criteria: SearchCriteria, term: ColumnElement[str] | None, limit: int
    ) -> list[dict[str, Any]]:
        if criteria.ev_min is not None or criteria.ev_max is not None:
            return []
        full_name = Contact.first_name + " " + Contact.last_name
        query = select(Contact, Employment.company_id).outerjoin(
            Employment, (Employment.contact_id == Contact.id) & Employment.end_date.is_(None)
        )
        company_filters = self._company_filters(criteria)
        if company_filters:
            query = query.join(Company, Company.id == Employment.company_id).where(*company_filters)
        if term is not None:
            email = func.coalesce(Contact.email, "")
            query = query.where(or_(matches(full_name, term), matches(email, term))).order_by(
                func.greatest(rank(full_name, term), rank(email, term)).desc(), Contact.last_name
            )
        else:
            query = query.order_by(Contact.last_name, Contact.first_name)
        rows = list((await db.execute(query.limit(limit))).tuples())
        holders = await self.contacts.holders(db, [contact.id for contact, _ in rows])
        return [
            {
                "id": contact.id,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "email": contact.email,
                "company_id": company_id,
                "relationship_holders": holders[contact.id],
            }
            for contact, company_id in rows
        ]

    async def _deals(
        self,
        db: AsyncSession,
        user: dict[str, Any],
        criteria: SearchCriteria,
        term: ColumnElement[str] | None,
        now: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        if criteria.company_types or criteria.country_ids:
            return []
        # Code name only: matching on the client or target would reveal them through the result.
        query = DealPolicy(now).visible(user, select(Mandate))
        if criteria.sector_ids:
            query = query.where(Mandate.sector_id.in_(criteria.sector_ids))
        if criteria.ev_min is not None:
            query = query.where(Mandate.estimated_ev >= criteria.ev_min)
        if criteria.ev_max is not None:
            query = query.where(Mandate.estimated_ev <= criteria.ev_max)
        if term is not None:
            query = query.where(matches(Mandate.code_name, term)).order_by(rank(Mandate.code_name, term).desc())
        query = query.order_by(Mandate.code_name)
        rows = (await db.execute(query.limit(limit))).scalars()
        return [{"id": m.id, "code_name": m.code_name, "stage": m.stage} for m in rows]


class SavedFilterService:
    async def _read(self, db: AsyncSession, saved: SavedFilter) -> dict[str, Any]:
        owner = await db.get(User, saved.owner_id)
        return {
            "id": saved.id,
            "owner_id": saved.owner_id,
            "owner_name": owner.name if owner else "",
            "name": saved.name,
            "criteria": saved.criteria,
            "shared": saved.shared,
            "created_at": saved.created_at,
        }

    async def create(
        self,
        db: AsyncSession,
        user: dict[str, Any],
        values: SavedFilterCreate,
        now: datetime,
        context: AuditContext | None = None,
    ) -> dict[str, Any]:
        saved = SavedFilter(
            owner_id=user["id"],
            name=values.name.strip(),
            criteria=values.criteria.model_dump(mode="json"),
            created_at=now,
            shared=values.shared,
        )
        db.add(saved)
        await db.flush()
        if context is not None:
            AuditService().record(
                db,
                context,
                "saved_filter.created",
                record_type="saved_filter",
                record_id=saved.id,
                new_values={"name": saved.name, "criteria": saved.criteria, "shared": saved.shared},
            )
        await db.commit()
        return await self._read(db, saved)

    async def visible(self, db: AsyncSession, user: dict[str, Any]) -> list[dict[str, Any]]:
        query = (
            select(SavedFilter)
            .where(or_(SavedFilter.owner_id == user["id"], SavedFilter.shared.is_(True)))
            .order_by(SavedFilter.name, SavedFilter.id)
        )
        return [await self._read(db, saved) for saved in (await db.execute(query)).scalars()]

    async def get(self, db: AsyncSession, user: dict[str, Any], filter_id: int) -> SavedFilter:
        saved = await db.get(SavedFilter, filter_id)
        if saved is None or (saved.owner_id != user["id"] and not saved.shared):
            raise SavedFilterNotFoundError(f"Saved filter {filter_id} not found")
        return saved

    async def set_shared(
        self, db: AsyncSession, user: dict[str, Any], filter_id: int, shared: bool, context: AuditContext | None = None
    ) -> dict[str, Any]:
        saved = await self.get(db, user, filter_id)
        if saved.owner_id != user["id"]:
            raise PermissionDeniedError("Only the owner shares a filter")
        if context is not None and saved.shared != shared:
            AuditService().record(
                db,
                context,
                "saved_filter.updated",
                record_type="saved_filter",
                record_id=saved.id,
                old_values={"shared": saved.shared},
                new_values={"shared": shared},
            )
        saved.shared = shared
        await db.commit()
        return await self._read(db, saved)

    async def delete(self, db: AsyncSession, user: dict[str, Any], filter_id: int, context: AuditContext | None = None) -> None:
        saved = await self.get(db, user, filter_id)
        if saved.owner_id != user["id"]:
            raise PermissionDeniedError("Only the owner deletes a filter")
        if context is not None:
            AuditService().record(
                db,
                context,
                "saved_filter.deleted",
                record_type="saved_filter",
                record_id=saved.id,
                old_values={"name": saved.name},
            )
        await db.delete(saved)
        await db.commit()
