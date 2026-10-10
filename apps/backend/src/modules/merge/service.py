"""Merging duplicate contacts or companies (CON-04).

The duplicate's rows move to the survivor, the duplicate is deleted, and a `RecordMerge` keeps
enough to put everything back. A row that would collide with one the survivor already has (the
same activity linked to both, the same colleague holding both) is dropped and kept in the merge.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Table, delete, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity.models import ActivityLink, Note
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import MergeBlockedError, MergeNotFoundError, UndoWindowClosedError, ValidationError
from ..company.models import Company, FinancialFigure
from ..company.service import normalize_name
from ..compliance.models import ConflictHit, DealCounterparty
from ..contact.models import Contact, Employment, RelationshipHolder
from ..contact.service import CONTACT_FIELDS
from ..mandate.models import Mandate
from ..mandate.policy import DealPolicy
from ..role.authorization import has_permission
from ..role.permissions import Permission
from ..task.models import Task
from .models import RecordMerge
from .schemas import MergeableType, MergeRequest, Pick

UNDO_WINDOW = timedelta(days=30)
UNDO_PERMISSION = Permission.SETTINGS_MANAGE
# Compliance is the only role that sees past the deal wall for this purpose (it holds the deal summary view).
WALL_MERGE_PERMISSION = Permission.DEALS_READ_SUMMARY

COMPANY_FIELDS = (
    "name",
    "type",
    "country_id",
    "sector_id",
    "enterprise_number",
    "vat_or_registry_number",
    "legal_form",
    "nace_code",
    "address",
)


@dataclass(frozen=True)
class Reference:
    """A column that points at a merged record. `kind` narrows polymorphic links; `unique_with`
    names the other columns of a unique index, so a collision on the survivor drops the row."""

    key: str
    table: Table
    column: str
    kind: str | None = None
    unique_with: tuple[str, ...] = ()


def _polymorphic(record_type: str) -> list[Reference]:
    return [
        Reference(
            f"activity_links.{record_type}",
            ActivityLink.__table__,  # type: ignore[arg-type]
            "record_id",
            record_type,
            ("activity_id", "record_type"),
        ),
        Reference(f"notes.{record_type}", Note.__table__, "record_id", record_type),  # type: ignore[arg-type]
        Reference(f"tasks.{record_type}", Task.__table__, "record_id", record_type),  # type: ignore[arg-type]
    ]


REFERENCES: dict[MergeableType, list[Reference]] = {
    MergeableType.CONTACT: [
        Reference("employments", Employment.__table__, "contact_id"),  # type: ignore[arg-type]
        Reference("relationship_holders", RelationshipHolder.__table__, "contact_id", None, ("user_id",)),  # type: ignore[arg-type]
        *_polymorphic("contact"),
    ],
    MergeableType.COMPANY: [
        Reference("employments", Employment.__table__, "company_id"),  # type: ignore[arg-type]
        Reference("deals_as_client", Mandate.__table__, "client_id"),  # type: ignore[arg-type]
        Reference("deals_as_target", Mandate.__table__, "target_id"),  # type: ignore[arg-type]
        Reference("subsidiaries", Company.__table__, "parent_id"),  # type: ignore[arg-type]
        Reference(
            "financials",
            FinancialFigure.__table__,  # type: ignore[arg-type]
            "company_id",
            None,
            ("year", "metric", "source"),
        ),
        Reference("deal_counterparties", DealCounterparty.__table__, "company_id", None, ("mandate_id",)),  # type: ignore[arg-type]
        Reference("conflict_hits", ConflictHit.__table__, "company_id"),  # type: ignore[arg-type]
        Reference("conflict_hits.matched", ConflictHit.__table__, "matched_company_id"),  # type: ignore[arg-type]
        *_polymorphic("company"),
    ],
}

MODELS: dict[MergeableType, Any] = {MergeableType.CONTACT: Contact, MergeableType.COMPANY: Company}
FIELDS = {MergeableType.CONTACT: CONTACT_FIELDS, MergeableType.COMPANY: COMPANY_FIELDS}


def _json(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _snapshot(table: Table, row: Any) -> dict[str, Any]:
    return {column.name: _json(row[column.name]) for column in table.columns}


def _revive(table: Table, values: dict[str, Any]) -> dict[str, Any]:
    revived: dict[str, Any] = {}
    for name, value in values.items():
        python_type = table.columns[name].type.python_type
        if value is not None and python_type is datetime:
            value = datetime.fromisoformat(value)
        elif value is not None and python_type is date:
            value = date.fromisoformat(value)
        elif value is not None and python_type is Decimal:
            value = Decimal(value)
        revived[name] = value
    return revived


def _where(reference: Reference, record_id: int) -> list[Any]:
    clauses = [reference.table.c[reference.column] == record_id]
    if reference.kind is not None:
        clauses.append(reference.table.c.record_type == reference.kind)
    return clauses


class MergeService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def _record(self, db: AsyncSession, record_type: MergeableType, record_id: int) -> Any:
        record = await db.get(MODELS[record_type], record_id)
        if record is None:
            raise ValidationError(f"{record_type.value} {record_id} not found", field="survivor_id")
        return record

    async def deals_of(self, db: AsyncSession, record_type: MergeableType, record_id: int) -> set[int]:
        """Every deal the record sits on: as client or target, through the contact's company, or
        on an activity, note or task linked to both."""
        if record_type == MergeableType.COMPANY:
            companies = select(Company.id).where(Company.id == record_id)
        else:
            companies = select(Employment.company_id).where(Employment.contact_id == record_id, Employment.end_date.is_(None))
        deals = set(
            (
                await db.execute(
                    select(Mandate.id).where(or_(Mandate.client_id.in_(companies), Mandate.target_id.in_(companies)))
                )
            ).scalars()
        )
        activities = select(ActivityLink.activity_id).where(
            ActivityLink.record_type == record_type.value, ActivityLink.record_id == record_id
        )
        deals |= set(
            (
                await db.execute(
                    select(ActivityLink.record_id).where(
                        ActivityLink.activity_id.in_(activities), ActivityLink.record_type == "mandate"
                    )
                )
            ).scalars()
        )
        for model in (Note, Task):
            linked = select(model.mandate_id).where(
                model.record_type == record_type.value, model.record_id == record_id, model.mandate_id.is_not(None)
            )
            deals |= {mandate_id for mandate_id in (await db.execute(linked)).scalars() if mandate_id is not None}
        return deals

    async def _check_wall(self, db: AsyncSession, user: dict[str, Any], values: MergeRequest, now: datetime) -> None:
        if has_permission(user, WALL_MERGE_PERMISSION):
            return
        visible = set(await DealPolicy(now).visible_mandate_ids(db, user))
        for record_id in (values.survivor_id, values.duplicate_id):
            if await self.deals_of(db, values.record_type, record_id) - visible:
                raise MergeBlockedError("Record on a deal the caller cannot access")

    async def merge(
        self, db: AsyncSession, user: dict[str, Any], values: MergeRequest, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        record_type = values.record_type
        fields = FIELDS[record_type]
        unknown = sorted(set(values.fields) - set(fields))
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(unknown)}", field="fields")
        survivor = await self._record(db, record_type, values.survivor_id)
        duplicate = await self._record(db, record_type, values.duplicate_id)
        await self._check_wall(db, user, values, now)

        table: Table = MODELS[record_type].__table__
        duplicate_row = (await db.execute(select(table).where(table.c.id == duplicate.id))).mappings().one()
        survivor_row = (await db.execute(select(table).where(table.c.id == survivor.id))).mappings().one()

        moved: dict[str, list[int]] = {}
        dropped: dict[str, list[dict[str, Any]]] = {}
        for reference in REFERENCES[record_type]:
            rows = (await db.execute(select(reference.table).where(*_where(reference, duplicate.id)))).mappings().all()
            for row in rows:
                if reference.key == "subsidiaries" and row["id"] == survivor.id:
                    continue
                collides = False
                if reference.unique_with:
                    clash = select(reference.table.c.id).where(
                        *_where(reference, survivor.id),
                        *[reference.table.c[column] == row[column] for column in reference.unique_with],
                    )
                    collides = (await db.execute(clash)).first() is not None
                if collides:
                    dropped.setdefault(reference.key, []).append(_snapshot(reference.table, row))
                    await db.execute(delete(reference.table).where(reference.table.c.id == row["id"]))
                else:
                    moved.setdefault(reference.key, []).append(row["id"])
                    await db.execute(
                        update(reference.table).where(reference.table.c.id == row["id"]).values({reference.column: survivor.id})
                    )

        survivor_before = _snapshot(table, survivor_row)
        picked = {field: duplicate_row[field] for field, pick in values.fields.items() if pick == Pick.DUPLICATE}
        # The duplicate goes first, so a unique value it hands over (an enterprise number) is free.
        await db.execute(delete(table).where(table.c.id == duplicate.id))
        if record_type == MergeableType.COMPANY:
            if survivor_row["parent_id"] == duplicate.id:
                picked.setdefault(
                    "parent_id", duplicate_row["parent_id"] if duplicate_row["parent_id"] != survivor.id else None
                )
            if "name" in picked:
                picked["normalized_name"] = normalize_name(picked["name"])
        if picked:
            await db.execute(update(table).where(table.c.id == survivor.id).values(picked))

        merge = RecordMerge(
            record_type=record_type.value,
            survivor_id=survivor.id,
            duplicate_id=duplicate.id,
            merged_by=user["id"],
            merged_at=now,
            duplicate_snapshot=_snapshot(table, duplicate_row),
            survivor_before=survivor_before,
            moved=moved,
            dropped=dropped,
        )
        db.add(merge)
        await db.flush()
        self.audit.record(
            db,
            context,
            f"{record_type.value}.merged",
            record_type=record_type.value,
            record_id=survivor.id,
            old_values={"survivor": survivor_before, "duplicate": merge.duplicate_snapshot},
            new_values={
                "merge_id": merge.id,
                "picked": {key: _json(value) for key, value in picked.items()},
                "moved": {key: len(ids) for key, ids in moved.items()},
            },
        )
        result = self.read(merge)
        await db.commit()
        db.expire_all()
        return result

    async def undo(self, db: AsyncSession, merge_id: int, context: AuditContext) -> dict[str, Any]:
        now = context.clock.now()
        merge = await db.get(RecordMerge, merge_id)
        if merge is None:
            raise MergeNotFoundError(f"Merge {merge_id} not found")
        if merge.undone_at is not None or now - merge.merged_at > UNDO_WINDOW:
            raise UndoWindowClosedError("Undo window closed")
        record_type = MergeableType(merge.record_type)
        table: Table = MODELS[record_type].__table__

        restored_fields = {
            key: value
            for key, value in _revive(table, merge.survivor_before).items()
            if key not in ("id", "created_at", "updated_at")
        }
        # Free the survivor's unique values before the duplicate takes its own back.
        await db.execute(update(table).where(table.c.id == merge.survivor_id).values(restored_fields))
        await db.execute(insert(table).values(_revive(table, merge.duplicate_snapshot)))
        references = {reference.key: reference for reference in REFERENCES[record_type]}
        for key, ids in merge.moved.items():
            reference = references[key]
            await db.execute(
                update(reference.table).where(reference.table.c.id.in_(ids)).values({reference.column: merge.duplicate_id})
            )
        for key, rows in merge.dropped.items():
            reference = references[key]
            for row in rows:
                await db.execute(insert(reference.table).values(_revive(reference.table, row)))

        merge.undone_at = now
        merge.undone_by = context.user_id
        self.audit.record(
            db,
            context,
            f"{record_type.value}.merge_undone",
            record_type=record_type.value,
            record_id=merge.survivor_id,
            new_values={"merge_id": merge.id, "restored_id": merge.duplicate_id},
        )
        result = self.read(merge)
        await db.commit()
        db.expire_all()
        return result

    async def recent(self, db: AsyncSession, now: datetime) -> list[dict[str, Any]]:
        query = (
            select(RecordMerge)
            .where(RecordMerge.merged_at >= now - UNDO_WINDOW, RecordMerge.undone_at.is_(None))
            .order_by(RecordMerge.merged_at.desc())
        )
        return [self.read(merge) for merge in (await db.execute(query)).scalars()]

    @staticmethod
    def read(merge: RecordMerge) -> dict[str, Any]:
        return {
            "id": merge.id,
            "record_type": merge.record_type,
            "survivor_id": merge.survivor_id,
            "duplicate_id": merge.duplicate_id,
            "merged_by": merge.merged_by,
            "merged_at": merge.merged_at,
            "moved": {key: len(ids) for key, ids in merge.moved.items()},
            "undone_at": merge.undone_at,
        }
