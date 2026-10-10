from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import PicklistValueExistsError, PicklistValueInUseError, PicklistValueNotFoundError, ValidationError
from .models import PicklistValue
from .schemas import Language, PicklistKind, PicklistValueCreate, PicklistValueRead, PicklistValueUpdate

DEFAULT_COUNTRIES = {
    "BE": ("Belgium", "Belgique", "België"),
    "NL": ("Netherlands", "Pays-Bas", "Nederland"),
    "FR": ("France", "France", "Frankrijk"),
    "LU": ("Luxembourg", "Luxembourg", "Luxemburg"),
    "DE": ("Germany", "Allemagne", "Duitsland"),
    "GB": ("United Kingdom", "Royaume-Uni", "Verenigd Koninkrijk"),
    "US": ("United States", "États-Unis", "Verenigde Staten"),
}


async def seed_default_picklists(db: AsyncSession) -> None:
    """Adds missing default countries; never touches values an admin renamed or deactivated."""
    existing = set(
        (await db.execute(select(PicklistValue.code).where(PicklistValue.kind == PicklistKind.COUNTRY.value))).scalars()
    )
    for code, (en, fr, nl) in DEFAULT_COUNTRIES.items():
        if code not in existing:
            db.add(PicklistValue(kind=PicklistKind.COUNTRY.value, code=code, label_en=en, label_fr=fr, label_nl=nl))
    await db.commit()


def to_read(value: PicklistValue, lang: Language = Language.EN) -> dict[str, Any]:
    label = getattr(value, f"label_{lang.value}") or value.label_en
    return PicklistValueRead(
        id=value.id,
        kind=PicklistKind(value.kind),
        code=value.code,
        label_en=value.label_en,
        label_fr=value.label_fr,
        label_nl=value.label_nl,
        is_active=value.is_active,
        label=label,
        translated=bool(value.label_fr and value.label_nl),
    ).model_dump()


class PicklistService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def get(self, db: AsyncSession, value_id: int) -> PicklistValue:
        value = await db.get(PicklistValue, value_id)
        if value is None:
            raise PicklistValueNotFoundError(f"Picklist value {value_id} not found")
        return value

    async def require_active(self, db: AsyncSession, value_id: int, kind: PicklistKind) -> PicklistValue:
        value = await db.get(PicklistValue, value_id)
        if value is None or value.kind != kind.value or not value.is_active:
            raise ValidationError(f"{kind.value} {value_id} is not an active {kind.value} value", field=f"{kind.value}_id")
        return value

    async def list_values(
        self, db: AsyncSession, kind: PicklistKind | None, lang: Language, include_inactive: bool
    ) -> list[dict[str, Any]]:
        query = select(PicklistValue).order_by(PicklistValue.kind, PicklistValue.label_en)
        if kind is not None:
            query = query.where(PicklistValue.kind == kind.value)
        if not include_inactive:
            query = query.where(PicklistValue.is_active.is_(True))
        return [to_read(value, lang) for value in (await db.execute(query)).scalars()]

    async def create(self, db: AsyncSession, values: PicklistValueCreate, context: AuditContext) -> dict[str, Any]:
        value = PicklistValue(**values.model_dump(mode="json"))
        db.add(value)
        try:
            await db.flush()
        except IntegrityError as error:
            await db.rollback()
            raise PicklistValueExistsError("A value with this code already exists") from error
        self.audit.record(
            db,
            context,
            "picklist.created",
            record_type="picklist_value",
            record_id=value.id,
            new_values=values.model_dump(mode="json"),
        )
        await db.commit()
        return to_read(value)

    async def update(
        self, db: AsyncSession, value_id: int, values: PicklistValueUpdate, context: AuditContext
    ) -> dict[str, Any]:
        value = await self.get(db, value_id)
        changes = values.model_dump(exclude_unset=True)
        old = {key: getattr(value, key) for key in changes}
        for key, new in changes.items():
            setattr(value, key, new)
        self.audit.record(
            db,
            context,
            "picklist.updated",
            record_type="picklist_value",
            record_id=value.id,
            old_values=old,
            new_values=changes,
        )
        await db.commit()
        return to_read(value)

    async def delete(self, db: AsyncSession, value_id: int, context: AuditContext) -> None:
        value = await self.get(db, value_id)
        snapshot = {"kind": value.kind, "code": value.code, "label_en": value.label_en}
        # Every table that references a picklist value does so with ON DELETE RESTRICT, so the
        # database itself tells us whether the value is in use, including tables added later.
        await db.delete(value)
        try:
            await db.flush()
        except IntegrityError as error:
            await db.rollback()
            raise PicklistValueInUseError("In use: rename or deactivate it instead") from error
        self.audit.record(
            db, context, "picklist.deleted", record_type="picklist_value", record_id=value_id, old_values=snapshot
        )
        await db.commit()
