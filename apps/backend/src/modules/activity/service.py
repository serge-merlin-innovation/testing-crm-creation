from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ActivityNotFoundError, CompanyNotFoundError, PermissionDeniedError, RestoreWindowClosedError
from ..company.models import Company
from ..contact.service import ContactService
from ..mandate.models import Mandate
from ..mandate.policy import DealAction, DealPolicy, record_view
from ..role.authorization import has_permission
from ..role.permissions import Permission
from ..user.models import User
from ..user.service import display_name
from .models import Activity, ActivityLink, Note
from .schemas import ActivityCreate, ActivityUpdate, NoteCreate, NoteRead, NoteVisibility, RecordRef, RecordType

# An edit within this window of logging is a correction, not shown as an edit.
EDIT_GRACE = timedelta(days=7)
RESTORE_WINDOW = timedelta(days=30)
RESTORE_PERMISSION = Permission.SETTINGS_MANAGE


async def require_record(db: AsyncSession, user: dict[str, Any], ref: RecordRef, now: datetime, action: DealAction) -> None:
    """404 for a missing record, and for a deal the caller may not see."""
    if ref.record_type == RecordType.CONTACT:
        await ContactService().get(db, ref.record_id)
    elif ref.record_type == RecordType.COMPANY:
        if await db.get(Company, ref.record_id) is None:
            raise CompanyNotFoundError(f"Company {ref.record_id} not found")
    else:
        await DealPolicy(now).authorize(db, user, ref.record_id, action)


async def require_timeline(
    db: AsyncSession, user: dict[str, Any], ref: RecordRef, now: datetime, context: AuditContext
) -> None:
    """A deal's timeline is a deal read: it is logged as a view (AUD-01 c1)."""
    if ref.record_type == RecordType.MANDATE:
        await record_view(db, await DealPolicy(now).authorize(db, user, ref.record_id, DealAction.READ), context)
    else:
        await require_record(db, user, ref, now, DealAction.READ)


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


class ActivityService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    def _read(self, activity: Activity, links: Iterable[ActivityLink]) -> dict[str, Any]:
        edited = activity.updated_at is not None and activity.updated_at - activity.created_at > EDIT_GRACE
        return {
            "id": activity.id,
            "type": activity.type,
            "occurred_at": activity.occurred_at,
            "participants": activity.participants,
            "note": activity.note,
            "author_id": activity.author_id,
            "created_at": activity.created_at,
            "links": [{"record_type": link.record_type, "record_id": link.record_id} for link in links],
            "edited_at": activity.updated_at if edited else None,
            "deleted_at": activity.deleted_at,
        }

    async def _links(self, db: AsyncSession, ids: list[int]) -> dict[int, list[ActivityLink]]:
        grouped: dict[int, list[ActivityLink]] = {activity_id: [] for activity_id in ids}
        if ids:
            query = select(ActivityLink).where(ActivityLink.activity_id.in_(ids)).order_by(ActivityLink.id)
            for link in (await db.execute(query)).scalars():
                grouped[link.activity_id].append(link)
        return grouped

    @staticmethod
    def _visible(links: list[ActivityLink], visible_mandates: set[int]) -> bool:
        return all(link.record_type != RecordType.MANDATE or link.record_id in visible_mandates for link in links)

    async def _get_visible(self, db: AsyncSession, user: dict[str, Any], activity_id: int, now: datetime) -> Activity:
        activity = await db.get(Activity, activity_id)
        if activity is None or activity.deleted_at is not None:
            raise ActivityNotFoundError(f"Activity {activity_id} not found")
        links = (await self._links(db, [activity_id]))[activity_id]
        if not self._visible(links, set(await DealPolicy(now).visible_mandate_ids(db, user))):
            raise ActivityNotFoundError(f"Activity {activity_id} not found")
        return activity

    async def create(
        self, db: AsyncSession, user: dict[str, Any], values: ActivityCreate, now: datetime, context: AuditContext
    ) -> dict[str, Any]:
        refs = {(ref.record_type, ref.record_id): ref for ref in values.links}
        for ref in refs.values():
            await require_record(db, user, ref, now, DealAction.EDIT)
        activity = Activity(
            type=values.type.value,
            occurred_at=values.occurred_at,
            note=values.note,
            participants=list(values.participants),
            author_id=user["id"],
            created_at=now,
        )
        db.add(activity)
        await db.flush()
        links = [ActivityLink(activity_id=activity.id, record_type=kind.value, record_id=rid) for kind, rid in refs]
        db.add_all(links)
        self.audit.record(
            db,
            context,
            "activity.created",
            record_type="activity",
            record_id=activity.id,
            new_values={"type": activity.type, "links": [[kind.value, rid] for kind, rid in refs]},
            user_id=user["id"],
        )
        await db.commit()
        return self._read(activity, links)

    async def update(
        self,
        db: AsyncSession,
        user: dict[str, Any],
        activity_id: int,
        values: ActivityUpdate,
        now: datetime,
        context: AuditContext,
    ) -> dict[str, Any]:
        activity = await self._get_visible(db, user, activity_id, now)
        if activity.author_id != user["id"]:
            raise PermissionDeniedError("Only the author edits an activity")
        changes = values.model_dump(exclude_unset=True, exclude_none=True)
        old = {field: _plain(getattr(activity, field)) for field in changes}
        for field, value in changes.items():
            setattr(activity, field, value.value if field == "type" else value)
        if changes:
            activity.updated_at = now
            self.audit.record(
                db,
                context,
                "activity.updated",
                record_type="activity",
                record_id=activity.id,
                old_values=old,
                new_values={field: _plain(getattr(activity, field)) for field in changes},
            )
        await db.commit()
        return self._read(activity, (await self._links(db, [activity.id]))[activity.id])

    async def delete(
        self, db: AsyncSession, user: dict[str, Any], activity_id: int, now: datetime, context: AuditContext
    ) -> None:
        activity = await self._get_visible(db, user, activity_id, now)
        if activity.author_id != user["id"] and not has_permission(user, RESTORE_PERMISSION):
            raise PermissionDeniedError("Only the author or an admin deletes an activity")
        activity.deleted_at = now
        activity.deleted_by = user["id"]
        self.audit.record(db, context, "activity.deleted", record_type="activity", record_id=activity.id)
        await db.commit()

    async def restore(self, db: AsyncSession, activity_id: int, now: datetime, context: AuditContext) -> None:
        activity = await db.get(Activity, activity_id)
        if activity is None or activity.deleted_at is None:
            raise ActivityNotFoundError(f"Deleted activity {activity_id} not found")
        if now - activity.deleted_at > RESTORE_WINDOW:
            raise RestoreWindowClosedError("Deleted more than 30 days ago")
        activity.deleted_at = None
        activity.deleted_by = None
        self.audit.record(db, context, "activity.restored", record_type="activity", record_id=activity.id)
        await db.commit()

    async def deleted(self, db: AsyncSession, now: datetime) -> list[dict[str, Any]]:
        """Restorable activities for the admin bin: type and dates only, so a deal activity's content stays hidden."""
        query = (
            select(Activity)
            .where(Activity.deleted_at.is_not(None), Activity.deleted_at >= now - RESTORE_WINDOW)
            .order_by(Activity.deleted_at.desc())
        )
        return [
            {"id": a.id, "type": a.type, "occurred_at": a.occurred_at, "deleted_at": a.deleted_at, "deleted_by": a.deleted_by}
            for a in (await db.execute(query)).scalars()
        ]

    async def for_record(self, db: AsyncSession, ref: RecordRef, visible_mandates: set[int]) -> list[dict[str, Any]]:
        query = (
            select(Activity)
            .join(ActivityLink, ActivityLink.activity_id == Activity.id)
            .where(
                ActivityLink.record_type == ref.record_type.value,
                ActivityLink.record_id == ref.record_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc(), Activity.id.desc())
        )
        activities = list((await db.execute(query)).scalars())
        links = await self._links(db, [activity.id for activity in activities])
        return [
            self._read(activity, links[activity.id])
            for activity in activities
            if self._visible(links[activity.id], visible_mandates)
        ]


class NoteService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def create(
        self, db: AsyncSession, user: dict[str, Any], values: NoteCreate, now: datetime, context: AuditContext
    ) -> Note:
        ref = RecordRef(record_type=values.record_type, record_id=values.record_id)
        await require_record(db, user, ref, now, DealAction.EDIT)
        mandate_id = values.record_id if values.record_type == RecordType.MANDATE else values.mandate_id
        if mandate_id is not None and values.record_type != RecordType.MANDATE:
            await DealPolicy(now).authorize(db, user, mandate_id, DealAction.EDIT)
        note = Note(
            record_type=values.record_type.value,
            record_id=values.record_id,
            body=values.body,
            visibility=values.visibility.value,
            author_id=user["id"],
            created_at=now,
            mandate_id=mandate_id,
        )
        db.add(note)
        await db.flush()
        self.audit.record(
            db,
            context,
            "note.created",
            record_type="note",
            record_id=note.id,
            new_values={"record_type": note.record_type, "record_id": note.record_id, "visibility": note.visibility},
        )
        await db.commit()
        return note

    async def for_record(
        self, db: AsyncSession, user: dict[str, Any], ref: RecordRef, visible_mandates: set[int]
    ) -> list[Note]:
        query = (
            select(Note)
            .where(
                Note.record_type == ref.record_type.value,
                Note.record_id == ref.record_id,
                or_(Note.visibility != NoteVisibility.PRIVATE.value, Note.author_id == user["id"]),
                or_(Note.mandate_id.is_(None), Note.mandate_id.in_(visible_mandates)),
            )
            .order_by(Note.created_at.desc(), Note.id.desc())
        )
        return list((await db.execute(query)).scalars())


async def timeline(
    db: AsyncSession, user: dict[str, Any], ref: RecordRef, now: datetime, context: AuditContext
) -> dict[str, Any]:
    await require_timeline(db, user, ref, now, context)
    visible = set(await DealPolicy(now).visible_mandate_ids(db, user))
    deals: list[dict[str, Any]] = []
    if ref.record_type == RecordType.COMPANY:
        query = (
            select(Mandate.id, Mandate.code_name)
            .where(
                or_(Mandate.client_id == ref.record_id, Mandate.target_id == ref.record_id),
                Mandate.id.in_(visible),
            )
            .order_by(Mandate.code_name)
        )
        deals = [{"id": mid, "code_name": name} for mid, name in (await db.execute(query)).tuples()]
    activities = await ActivityService().for_record(db, ref, visible)
    notes = [
        {**NoteRead.model_validate(note, from_attributes=True).model_dump()}
        for note in await NoteService().for_record(db, user, ref, visible)
    ]
    author_ids = {item["author_id"] for item in (*activities, *notes)}
    authors = {
        uid: display_name(name, gone)
        for uid, name, gone in (
            await db.execute(select(User.id, User.name, User.is_deleted).where(User.id.in_(author_ids)))
        ).tuples()
    }
    for item in (*activities, *notes):
        item["author_name"] = authors.get(item["author_id"])
    return {"activities": activities, "notes": notes, "deals": deals}
