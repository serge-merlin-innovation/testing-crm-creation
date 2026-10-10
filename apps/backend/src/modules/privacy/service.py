import json
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity.models import Activity, ActivityLink, Note
from ..audit.models import AuditEntry
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ContactNotFoundError, PermissionDeniedError, ResourceNotFoundError
from ..contact.models import Contact, Employment
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..role.authorization import has_permission
from ..role.permissions import Permission
from ..user.models import User
from .models import LegalHold, RetentionPolicy, RetentionReview
from .schemas import ErasureResult, LegalHoldCreate, RetentionPolicyValues, ReviewDecision

ERASED = "[erased]"
DAYS_PER_YEAR = 365


class LegalHoldError(Exception):
    """Erasure refused; the message is the hold's reason, shown to compliance as is."""


def _jsonable(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _row(model: Any) -> dict[str, Any]:
    return {column.key: _jsonable(getattr(model, column.key)) for column in model.__table__.columns}


def _redact(text: str, identifiers: list[str]) -> str:
    for identifier in sorted(identifiers, key=len, reverse=True):
        text = re.sub(re.escape(identifier), ERASED, text, flags=re.IGNORECASE)
    return text


class PrivacyService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()

    async def _contact(self, db: AsyncSession, contact_id: int) -> Contact:
        contact = await db.get(Contact, contact_id)
        if contact is None:
            raise ContactNotFoundError(f"Contact {contact_id} not found")
        return contact

    async def _activities(self, db: AsyncSession, contact_id: int) -> list[Activity]:
        query = (
            select(Activity)
            .join(ActivityLink, ActivityLink.activity_id == Activity.id)
            .where(ActivityLink.record_type == "contact", ActivityLink.record_id == contact_id)
            .order_by(Activity.occurred_at, Activity.id)
        )
        return list((await db.execute(query)).scalars().unique())

    async def _notes(self, db: AsyncSession, contact_id: int) -> list[Note]:
        query = select(Note).where(Note.record_type == "contact", Note.record_id == contact_id).order_by(Note.id)
        return list((await db.execute(query)).scalars())

    async def export_person(self, db: AsyncSession, contact_id: int, context: AuditContext) -> tuple[str, str]:
        """Everything the CRM holds about one person, as a JSON file (GDPR access request)."""
        contact = await self._contact(db, contact_id)
        employments = (
            (await db.execute(select(Employment).where(Employment.contact_id == contact_id).order_by(Employment.id)))
            .scalars()
            .all()
        )
        activities = await self._activities(db, contact_id)
        links = (
            (await db.execute(select(ActivityLink).where(ActivityLink.activity_id.in_([a.id for a in activities]))))
            .scalars()
            .all()
        )
        notes = await self._notes(db, contact_id)
        holds = (await db.execute(select(LegalHold).where(LegalHold.contact_id == contact_id))).scalars().all()
        changes = (
            (
                await db.execute(
                    select(AuditEntry)
                    .where(AuditEntry.record_type == "contact", AuditEntry.record_id == str(contact_id))
                    .order_by(AuditEntry.created_at, AuditEntry.id)
                )
            )
            .scalars()
            .all()
        )
        document = {
            "exported_at": context.clock.now().isoformat(),
            "contact": _row(contact),
            "employments": [_row(e) for e in employments],
            "activities": [
                {**_row(a), "links": [_row(link) for link in links if link.activity_id == a.id]} for a in activities
            ],
            "notes": [_row(n) for n in notes],
            "legal_holds": [_row(h) for h in holds],
            "history": [
                {"action": e.action, "at": _jsonable(e.created_at), "old": e.old_values, "new": e.new_values} for e in changes
            ],
        }
        self.audit.record(
            db,
            context,
            "export",
            record_type="contact",
            record_id=contact_id,
            new_values={"kind": "person", "filter": {"contact_id": contact_id}, "rows": 1 + len(activities) + len(notes)},
        )
        await db.commit()
        return json.dumps(document, indent=2, default=str), f"person-{contact_id}.json"

    async def active_holds(self, db: AsyncSession, contact_id: int, now: datetime) -> list[LegalHold]:
        query = select(LegalHold).where(
            LegalHold.contact_id == contact_id,
            LegalHold.released_at.is_(None),
            or_(LegalHold.until.is_(None), LegalHold.until > now),
        )
        return list((await db.execute(query.order_by(LegalHold.id))).scalars())

    async def add_hold(self, db: AsyncSession, contact_id: int, values: LegalHoldCreate, context: AuditContext) -> LegalHold:
        await self._contact(db, contact_id)
        hold = LegalHold(
            contact_id=contact_id,
            reason=values.reason.strip(),
            created_by=context.user_id,
            created_at=context.clock.now(),
            until=values.until,
        )
        db.add(hold)
        await db.flush()
        self.audit.record(
            db, context, "legal_hold.added", record_type="contact", record_id=contact_id, new_values={"reason": hold.reason}
        )
        await db.commit()
        return hold

    async def holds(self, db: AsyncSession, contact_id: int) -> list[LegalHold]:
        await self._contact(db, contact_id)
        return list(
            (await db.execute(select(LegalHold).where(LegalHold.contact_id == contact_id).order_by(LegalHold.id))).scalars()
        )

    async def release_hold(self, db: AsyncSession, hold_id: int, context: AuditContext) -> None:
        hold = await db.get(LegalHold, hold_id)
        if hold is None:
            raise ResourceNotFoundError("Legal hold not found")
        if hold.released_at is None:
            hold.released_at = context.clock.now()
            self.audit.record(
                db,
                context,
                "legal_hold.released",
                record_type="contact",
                record_id=hold.contact_id,
                old_values={"reason": hold.reason},
            )
            await db.commit()

    async def erase(self, db: AsyncSession, contact_id: int, context: AuditContext) -> ErasureResult:
        contact = await self._contact(db, contact_id)
        now = context.clock.now()
        holds = await self.active_holds(db, contact_id, now)
        if holds:
            raise LegalHoldError("Erasure is blocked by a legal hold: " + "; ".join(hold.reason for hold in holds))

        full_name = f"{contact.first_name} {contact.last_name}"
        identifiers = [i for i in (full_name, contact.email, contact.phone, contact.first_name, contact.last_name) if i]
        identifiers = [i for i in identifiers if len(i) >= 2]

        activities = await self._activities(db, contact_id)
        for activity in activities:
            activity.note = _redact(activity.note, identifiers)
            activity.participants = [_redact(p, identifiers) for p in activity.participants]
        notes = await self._notes(db, contact_id)
        for note in notes:
            note.body = ERASED

        contact.first_name = "Erased"
        contact.last_name = f"contact {contact.id}"
        contact.email = None
        contact.phone = None
        contact.salutation = None
        contact.source = ERASED
        contact.do_not_contact = True
        for employment in (await db.execute(select(Employment).where(Employment.contact_id == contact_id))).scalars():
            employment.function = None
        self.audit.record(
            db,
            context,
            "contact.erased",
            record_type="contact",
            record_id=contact_id,
            new_values={"activities_cleaned": len(activities), "notes_cleaned": len(notes)},
        )
        await db.commit()
        return ErasureResult(contact_id=contact_id, activities_cleaned=len(activities), notes_cleaned=len(notes))

    async def policy(self, db: AsyncSession) -> RetentionPolicy:
        policy = await db.get(RetentionPolicy, 1)
        if policy is None:
            policy = RetentionPolicy(id=1)
            db.add(policy)
            await db.flush()
        return policy

    async def set_policy(self, db: AsyncSession, values: RetentionPolicyValues, context: AuditContext) -> RetentionPolicy:
        policy = await self.policy(db)
        old = policy.inactive_years
        policy.inactive_years = values.inactive_years
        self.audit.record(
            db,
            context,
            "retention.policy_changed",
            record_type="retention_policy",
            record_id=1,
            old_values={"inactive_years": old},
            new_values={"inactive_years": values.inactive_years},
        )
        await db.commit()
        return policy

    async def ask_owners(self, db: AsyncSession, now: datetime) -> int:
        """The monthly job: each inactive contact's owner is asked once to keep or anonymise it."""
        years = (await self.policy(db)).inactive_years
        cutoff = now - timedelta(days=DAYS_PER_YEAR * years)
        last_activity = (
            select(ActivityLink.record_id.label("contact_id"), func.max(Activity.occurred_at).label("last_at"))
            .join(Activity, Activity.id == ActivityLink.activity_id)
            .where(ActivityLink.record_type == "contact", Activity.deleted_at.is_(None))
            .group_by(ActivityLink.record_id)
            .subquery()
        )
        last_interaction = func.coalesce(last_activity.c.last_at, Contact.created_at)
        pending_or_kept = select(RetentionReview.id).where(
            RetentionReview.contact_id == Contact.id,
            or_(RetentionReview.decision.is_(None), RetentionReview.decided_at > cutoff),
        )
        rows = (
            await db.execute(
                select(Contact, last_interaction)
                .outerjoin(last_activity, last_activity.c.contact_id == Contact.id)
                .where(last_interaction < cutoff, Contact.first_name != "Erased", ~pending_or_kept.exists())
                .order_by(Contact.id)
            )
        ).all()
        for contact, last_at in rows:
            db.add(RetentionReview(contact_id=contact.id, owner_id=contact.owner_id, asked_at=now, last_interaction_at=last_at))
            owner = await db.get(User, contact.owner_id) if contact.owner_id else None
            if owner is not None and not owner.is_deleted:
                await self.notifications.add(
                    db,
                    Message(
                        user_id=owner.id,
                        email=owner.email,
                        kind=EventKind.RETENTION_REVIEW.value,
                        title="Keep or anonymise an inactive contact",
                        body=f"{contact.first_name} {contact.last_name} has had no interaction for {years} years. "
                        "Decide whether to keep or anonymise the contact.",
                        link="/privacy",
                    ),
                    now,
                )
        await db.commit()
        await self.notifications.flush_emails()
        return len(rows)

    async def reviews(self, db: AsyncSession, user: dict[str, Any], everyone: bool) -> list[dict[str, Any]]:
        query = (
            select(RetentionReview, Contact.first_name, Contact.last_name)
            .join(Contact, Contact.id == RetentionReview.contact_id)
            .where(RetentionReview.decision.is_(None))
            .order_by(RetentionReview.asked_at, RetentionReview.id)
        )
        if not everyone:
            query = query.where(RetentionReview.owner_id == user["id"])
        return [
            {
                "id": review.id,
                "contact_id": review.contact_id,
                "contact_name": f"{first} {last}",
                "owner_id": review.owner_id,
                "asked_at": review.asked_at,
                "last_interaction_at": review.last_interaction_at,
                "decision": review.decision,
                "decided_at": review.decided_at,
            }
            for review, first, last in (await db.execute(query)).tuples()
        ]

    async def decide(
        self, db: AsyncSession, user: dict[str, Any], review_id: int, decision: ReviewDecision, context: AuditContext
    ) -> None:
        review = await db.get(RetentionReview, review_id)
        if review is None:
            raise ResourceNotFoundError("Review not found")
        if review.owner_id != user["id"] and not has_permission(user, Permission.PRIVACY_MANAGE):
            raise PermissionDeniedError("Only the owner or compliance decides")
        if decision == ReviewDecision.ANONYMISE:
            await self.erase(db, review.contact_id, context)
        review.decision = decision.value
        review.decided_at = context.clock.now()
        review.decided_by = user["id"]
        self.audit.record(
            db,
            context,
            "retention.decided",
            record_type="contact",
            record_id=review.contact_id,
            new_values={"decision": decision.value},
        )
        await db.commit()
