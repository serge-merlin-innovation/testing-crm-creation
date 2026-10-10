from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..common.exceptions import PermissionDeniedError, ResourceExistsError
from ..fee.schemas import FeeTermsValues
from ..role.authorization import has_permission, require_permission
from ..role.permissions import Permission
from .dependencies import OriginationServiceDep
from .schemas import (
    ConflictWarning,
    CredentialCreate,
    CredentialRead,
    LinkCreate,
    LinkRead,
    MemberCreate,
    MemberRead,
    OpportunityCreate,
    OpportunityListItem,
    OpportunityRead,
    OpportunityStage,
    OriginationSettingsValues,
    StageChange,
    WinRead,
    WinRequest,
)
from .service import can_see_opportunities, has_active_mandate

router = APIRouter(tags=["Origination"])

CreatorDep = Annotated[dict[str, Any], require_permission(Permission.MANDATES_CREATE)]
SettingsDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]
HIDDEN: dict[int | str, dict[str, Any]] = {
    404: {"description": "Not found, or not the owner nor invited (the two are indistinguishable)"}
}


def _reader(user: dict[str, Any]) -> None:
    if not can_see_opportunities(user):
        raise PermissionDeniedError("Missing deals.read_staffed")


@router.get("/stages", response_model=list[OpportunityStage], summary="The origination stages, in order")
async def list_stages(_: CurrentUserDep) -> list[OpportunityStage]:
    return list(OpportunityStage)


@router.get(
    "/opportunities",
    response_model=list[OpportunityListItem],
    summary="The origination pipeline: opportunities I own or was invited to",
)
async def list_opportunities(
    db: AsyncSessionDep, service: OriginationServiceDep, user: CurrentUserDep, stage: OpportunityStage | None = None
) -> list[dict[str, Any]]:
    return await service.list_visible(db, user, stage)


@router.post(
    "/opportunities",
    status_code=201,
    response_model=OpportunityRead,
    response_model_exclude_unset=True,
    summary="Log an opportunity (partners)",
    description="`conflict_warning` is true when the company or its group is on an active mandate.",
)
async def create_opportunity(
    values: OpportunityCreate,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CreatorDep,
) -> dict[str, Any]:
    _reader(user)
    opportunity = await service.create(db, values, context)
    return await service.read(db, user, opportunity)


@router.get(
    "/conflict-warning",
    response_model=ConflictWarning,
    summary="Whether a company is on an active mandate (no deal is named)",
)
async def conflict_warning(db: AsyncSessionDep, user: CreatorDep, company_id: int) -> dict[str, bool]:
    return {"conflict_warning": await has_active_mandate(db, company_id)}


@router.get(
    "/credentials",
    response_model=list[CredentialRead],
    summary="Search credentials: closed deals with a tombstone allowed",
    description="`ev_min` and `ev_max` filter the final EV in EUR thousands. Code names only.",
)
async def search_credentials(
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    user: CurrentUserDep,
    sector_id: int | None = None,
    ev_min: Decimal | None = None,
    ev_max: Decimal | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    _reader(user)
    return await service.search_credentials(db, sector_id, ev_min, ev_max, q)


@router.get("/settings", response_model=OriginationSettingsValues, summary="Dormant-prospect threshold")
async def get_settings(db: AsyncSessionDep, service: OriginationServiceDep, _: CurrentUserDep) -> Any:
    row = await service.settings(db)
    await db.commit()
    return {"dormant_days": row.dormant_days}


@router.put("/settings", response_model=OriginationSettingsValues, summary="Change the dormant-prospect threshold (Admin)")
async def put_settings(
    values: OriginationSettingsValues,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    _: SettingsDep,
) -> Any:
    row = await service.update_settings(db, values, context)
    return {"dormant_days": row.dormant_days}


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityRead,
    response_model_exclude_unset=True,
    summary="An opportunity",
    responses=HIDDEN,
)
async def get_opportunity(
    opportunity_id: int, db: AsyncSessionDep, service: OriginationServiceDep, user: CurrentUserDep
) -> dict[str, Any]:
    return await service.read(db, user, await service.get(db, user, opportunity_id))


@router.post(
    "/opportunities/{opportunity_id}/stage",
    response_model=OpportunityRead,
    response_model_exclude_unset=True,
    summary="Move an opportunity",
    description="Lost needs `lost_reason` (`competitor_advisor` optional); On hold needs `revisit_date`. Won: /win.",
    responses=HIDDEN,
)
async def move_opportunity(
    opportunity_id: int,
    values: StageChange,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    opportunity = await service.editable(db, user, opportunity_id)
    await service.change_stage(db, opportunity, values, context)
    return await service.read(db, user, opportunity)


@router.post(
    "/opportunities/{opportunity_id}/win",
    status_code=201,
    response_model=WinRead,
    summary="Confirm Won: create the mandate (owner)",
    description="Company, invited team and fee draft are copied; the mandate goes through the conflict check.",
    responses=HIDDEN,
)
async def win_opportunity(
    opportunity_id: int,
    values: WinRequest,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    opportunity = await service.get(db, user, opportunity_id)
    if opportunity.mandate_id is not None:
        raise HTTPException(status_code=409, detail="This opportunity is already won.")
    if opportunity.owner_id != user["id"] or not has_permission(user, Permission.MANDATES_CREATE):
        raise PermissionDeniedError("Only the owner confirms Won")
    opportunity = await service.editable(db, user, opportunity_id)
    mandate = await service.win(db, opportunity, values, context)
    return {"id": opportunity.id, "stage": opportunity.stage, "mandate_id": mandate.id}


@router.put(
    "/opportunities/{opportunity_id}/fee-draft",
    response_model=dict[str, Any],
    summary="Set the fee draft copied to the mandate on Won (fees.read)",
    responses=HIDDEN,
)
async def put_fee_draft(
    opportunity_id: int,
    values: FeeTermsValues,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> Any:
    opportunity = await service.editable(db, user, opportunity_id)
    if not has_permission(user, Permission.FEES_READ):
        raise PermissionDeniedError("Fee fields are hidden from this role")
    return await service.save_fee_draft(db, opportunity, values, context)


@router.post(
    "/opportunities/{opportunity_id}/members",
    status_code=201,
    response_model=OpportunityRead,
    response_model_exclude_unset=True,
    summary="Invite a colleague (owner)",
    responses=HIDDEN,
)
async def add_member(
    opportunity_id: int,
    values: MemberCreate,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    opportunity = await service.owned(db, user, opportunity_id)
    try:
        await service.add_member(db, opportunity, values.user_id, context)
    except ResourceExistsError as error:
        raise HTTPException(status_code=409, detail="This colleague already sees the opportunity.") from error
    return await service.read(db, user, opportunity)


@router.get(
    "/opportunities/{opportunity_id}/candidates",
    response_model=list[MemberRead],
    summary="Colleagues the owner can invite",
    responses=HIDDEN,
)
async def list_candidates(
    opportunity_id: int, db: AsyncSessionDep, service: OriginationServiceDep, user: CurrentUserDep
) -> list[dict[str, Any]]:
    return await service.candidates(db, await service.owned(db, user, opportunity_id))


@router.delete(
    "/opportunities/{opportunity_id}/members/{user_id}", status_code=204, summary="Remove an invitee (owner)", responses=HIDDEN
)
async def remove_member(
    opportunity_id: int,
    user_id: int,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> None:
    opportunity = await service.owned(db, user, opportunity_id)
    await service.remove_member(db, opportunity, user_id, context)


@router.post(
    "/opportunities/{opportunity_id}/links",
    status_code=201,
    response_model=LinkRead,
    summary="Link a pitch deck or document (https only)",
    responses=HIDDEN,
)
async def add_link(
    opportunity_id: int,
    values: LinkCreate,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> Any:
    return await service.add_link(db, await service.editable(db, user, opportunity_id), values, context)


@router.delete("/opportunities/{opportunity_id}/links/{link_id}", status_code=204, summary="Remove a link", responses=HIDDEN)
async def remove_link(
    opportunity_id: int, link_id: int, db: AsyncSessionDep, service: OriginationServiceDep, user: CurrentUserDep
) -> None:
    await service.remove_link(db, await service.editable(db, user, opportunity_id), link_id)


@router.post(
    "/opportunities/{opportunity_id}/credentials",
    status_code=201,
    response_model=CredentialRead,
    summary="Cite a past deal as a credential (closed, tombstone allowed)",
    responses=HIDDEN,
)
async def add_credential(
    opportunity_id: int,
    values: CredentialCreate,
    db: AsyncSessionDep,
    service: OriginationServiceDep,
    context: AuditContextDep,
    user: CurrentUserDep,
) -> Any:
    return await service.add_credential(db, await service.editable(db, user, opportunity_id), values, context)


@router.delete(
    "/opportunities/{opportunity_id}/credentials/{credential_id}",
    status_code=204,
    summary="Remove a credential (`credential_id` is the cited deal's id)",
    responses=HIDDEN,
)
async def remove_credential(
    opportunity_id: int, credential_id: int, db: AsyncSessionDep, service: OriginationServiceDep, user: CurrentUserDep
) -> None:
    await service.remove_credential(db, await service.editable(db, user, opportunity_id), credential_id)
