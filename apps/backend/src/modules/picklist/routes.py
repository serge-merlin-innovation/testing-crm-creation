from typing import Annotated, Any

from fastapi import APIRouter

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import PicklistServiceDep
from .schemas import Language, PicklistKind, PicklistValueCreate, PicklistValueRead, PicklistValueUpdate

router = APIRouter(tags=["Picklists"])

PicklistManagerDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]


@router.get("/", response_model=list[PicklistValueRead], summary="List picklist values, labelled in a language")
async def list_picklist_values(
    db: AsyncSessionDep,
    service: PicklistServiceDep,
    _: CurrentUserDep,
    kind: PicklistKind | None = None,
    lang: Language = Language.EN,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    return await service.list_values(db, kind, lang, include_inactive)


@router.post("/", status_code=201, response_model=PicklistValueRead, summary="Add a picklist value (Admin)")
async def create_picklist_value(
    values: PicklistValueCreate,
    db: AsyncSessionDep,
    service: PicklistServiceDep,
    context: AuditContextDep,
    _: PicklistManagerDep,
) -> dict[str, Any]:
    return await service.create(db, values, context)


@router.patch("/{value_id}", response_model=PicklistValueRead, summary="Rename, translate or deactivate a value (Admin)")
async def update_picklist_value(
    value_id: int,
    values: PicklistValueUpdate,
    db: AsyncSessionDep,
    service: PicklistServiceDep,
    context: AuditContextDep,
    _: PicklistManagerDep,
) -> dict[str, Any]:
    return await service.update(db, value_id, values, context)


@router.delete(
    "/{value_id}",
    status_code=204,
    summary="Delete an unused picklist value (Admin)",
    responses={409: {"description": "The value is in use: rename or deactivate it instead"}},
)
async def delete_picklist_value(
    value_id: int, db: AsyncSessionDep, service: PicklistServiceDep, context: AuditContextDep, _: PicklistManagerDep
) -> None:
    await service.delete(db, value_id, context)
