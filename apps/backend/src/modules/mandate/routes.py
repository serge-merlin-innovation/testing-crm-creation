from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..common.exceptions import LastLeadPartnerError, MandateExistsError, TeamMemberExistsError
from ..role.authorization import has_permission, require_permission
from ..role.permissions import Permission
from .dependencies import MandateServiceDep, PipelineServiceDep
from .pipeline import StageBlockedError, StaleVersion
from .policy import EditGrant, ReadGrant, ReopenGrant, SummaryGrant, TeamGrant
from .schemas import (
    DealFilters,
    DealLinkCreate,
    DealLinkRead,
    HistoryEntry,
    MandateClose,
    MandateCreate,
    MandateListItem,
    MandateRead,
    MandateReopen,
    MandateType,
    MandateUpdate,
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
    StageCriterionCreate,
    StageCriterionRead,
    StageMove,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
    UserOption,
    WallCrossingRead,
)
from .service import StaleVersionError
from .stages import DealStage

router = APIRouter(tags=["Mandates"])

MandateCreatorDep = Annotated[dict[str, Any], require_permission(Permission.MANDATES_CREATE)]
HIDDEN: dict[int | str, dict[str, Any]] = {
    404: {"description": "Not found, or not on the deal team (the two are indistinguishable)"}
}


@router.get(
    "/",
    response_model=list[MandateListItem],
    summary="Deals I am staffed on",
    description="Only deals you may read; `q` searches code names; partner, type, sector and stage filter.",
)
async def list_mandates(
    db: AsyncSessionDep,
    service: MandateServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    q: str | None = None,
    partner_id: int | None = None,
    type: MandateType | None = None,
    sector_id: int | None = None,
    stage: DealStage | None = None,
) -> list[dict[str, Any]]:
    filters = DealFilters(partner_id=partner_id, type=type, sector_id=sector_id, stage=stage)
    return await service.list_visible(db, user, clock.now(), q, filters)


@router.get("/lead-partners", response_model=list[UserOption], summary="Users who can lead a mandate")
async def list_lead_partners(db: AsyncSessionDep, service: MandateServiceDep, _: MandateCreatorDep) -> list[dict[str, Any]]:
    return await service.lead_partners(db)


@router.get(
    "/filters",
    summary="The deal filters offered to me",
    description="Fee filters appear only for roles that see fee fields (AUTHZ-06); they apply on GET /fees/.",
)
async def offered_filters(user: CurrentUserDep) -> dict[str, list[str]]:
    filters = ["q", "partner_id", "type", "sector_id", "stage"]
    if has_permission(user, Permission.FEES_READ):
        filters.append("min_expected_fee")
    return {"filters": filters}


@router.post(
    "/",
    status_code=201,
    response_model=MandateRead,
    summary="Create a mandate under a code name",
    responses={409: {"description": "Code name in use"}, 422: {"description": "Missing field or code name reveals a name"}},
)
async def create_mandate(
    values: MandateCreate,
    db: AsyncSessionDep,
    service: MandateServiceDep,
    context: AuditContextDep,
    _: MandateCreatorDep,
) -> dict[str, Any]:
    try:
        return await service.create(db, values, context)
    except MandateExistsError as error:
        raise HTTPException(status_code=409, detail="This code name is already in use.") from error


@router.get("/{mandate_id}", response_model=MandateRead, summary="One deal", responses=HIDDEN)
async def get_mandate(grant: ReadGrant, db: AsyncSessionDep, service: MandateServiceDep) -> dict[str, Any]:
    return await service.read(db, grant.mandate, grant)


@router.get(
    "/{mandate_id}/summary",
    response_model=MandateRead,
    summary="Read-only deal summary (team, or back-office on any deal)",
    description="Compliance / back-office read it on deals they are not staffed on (ROLE-01). Never editable here.",
    responses=HIDDEN,
)
async def get_mandate_summary(grant: SummaryGrant, db: AsyncSessionDep, service: MandateServiceDep) -> dict[str, Any]:
    return await service.read(db, grant.mandate, grant)


@router.patch(
    "/{mandate_id}",
    response_model=MandateRead,
    summary="Edit a deal",
    responses={**HIDDEN, 409: {"description": "Stale version: `detail.current` is the newer deal"}},
)
async def update_mandate(
    values: MandateUpdate, grant: EditGrant, db: AsyncSessionDep, service: MandateServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    try:
        return await service.update(db, grant, values, context)
    except StaleVersionError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Someone changed this deal since you opened it. Review the newer version and try again.",
                "current": error.current,
            },
        ) from error
    except MandateExistsError as error:
        raise _conflict("This code name is already in use.") from error


@router.get("/{mandate_id}/history", response_model=list[HistoryEntry], summary="Who changed what, when", responses=HIDDEN)
async def get_history(grant: ReadGrant, db: AsyncSessionDep, service: MandateServiceDep) -> list[dict[str, Any]]:
    return await service.history(db, grant.mandate.id)


@router.get("/{mandate_id}/team", response_model=TeamRead, summary="The deal team", responses=HIDDEN)
async def get_team(grant: ReadGrant, db: AsyncSessionDep, service: MandateServiceDep, clock: ClockDep) -> dict[str, Any]:
    return await service.team(db, grant, clock.now())


@router.get(
    "/{mandate_id}/team/candidates", response_model=list[UserOption], summary="Users who can be added", responses=HIDDEN
)
async def get_team_candidates(grant: TeamGrant, db: AsyncSessionDep, service: MandateServiceDep) -> list[dict[str, Any]]:
    return await service.candidates(db, grant)


@router.post(
    "/{mandate_id}/team",
    status_code=201,
    response_model=TeamMemberRead,
    summary="Add a team member (deal partner or director)",
    responses=HIDDEN,
)
async def add_team_member(
    values: TeamMemberCreate, grant: TeamGrant, db: AsyncSessionDep, service: MandateServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    try:
        return await service.add_member(db, grant, values, context)
    except TeamMemberExistsError as error:
        raise _conflict("This user is already on the deal team.") from error


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


@router.delete(
    "/{mandate_id}/team/{user_id}",
    status_code=204,
    summary="Remove a team member (deal partner or director)",
    responses={**HIDDEN, 409: {"description": "The last lead partner cannot be removed"}},
)
async def remove_team_member(
    user_id: int, grant: TeamGrant, db: AsyncSessionDep, service: MandateServiceDep, context: AuditContextDep
) -> Response:
    try:
        await service.remove_member(db, grant, user_id, context)
    except LastLeadPartnerError as error:
        raise _conflict("Every deal needs one lead partner: add another lead partner before removing this one.") from error
    return Response(status_code=204)


@router.get(
    "/{mandate_id}/wall-crossings",
    response_model=list[WallCrossingRead],
    summary="The deal's wall-crossing register",
    responses=HIDDEN,
)
async def get_wall_crossings(grant: ReadGrant, db: AsyncSessionDep, service: MandateServiceDep) -> list[dict[str, Any]]:
    return await service.wall_crossings(db, grant.mandate.id)


@router.get("/{mandate_id}/links", response_model=list[DealLinkRead], summary="Document links", responses=HIDDEN)
async def get_links(grant: ReadGrant, db: AsyncSessionDep, service: MandateServiceDep) -> list[Any]:
    return await service.links(db, grant.mandate.id)


@router.post(
    "/{mandate_id}/links",
    status_code=201,
    response_model=DealLinkRead,
    summary="Add a labelled https link (file server, VDR)",
    responses=HIDDEN,
)
async def add_link(
    values: DealLinkCreate, grant: EditGrant, db: AsyncSessionDep, service: MandateServiceDep, context: AuditContextDep
) -> Any:
    return await service.add_link(db, grant, values, context)


@router.delete("/{mandate_id}/links/{link_id}", status_code=204, summary="Remove a link", responses=HIDDEN)
async def remove_link(
    link_id: int, grant: EditGrant, db: AsyncSessionDep, service: MandateServiceDep, context: AuditContextDep
) -> Response:
    await service.remove_link(db, grant, link_id, context)
    return Response(status_code=204)


STALE = "Someone changed this deal since you opened it. Reload it and try again."


async def _stale(db: AsyncSessionDep, service: MandateServiceDep, grant: Any) -> HTTPException:
    current = await service.read(db, grant.mandate, grant)
    await db.rollback()
    return HTTPException(status_code=409, detail={"message": STALE, "current": current})


@router.post(
    "/{mandate_id}/stage",
    response_model=MandateRead,
    summary="Move a deal to another stage",
    description="Forward moves must meet every exit criterion of the stages left; backward moves need a reason.",
    responses={
        **HIDDEN,
        409: {"description": "Stale version"},
        422: {"description": "Exit criteria missing (`detail.reasons`) or reason missing"},
    },
)
async def move_stage(
    values: StageMove,
    grant: EditGrant,
    db: AsyncSessionDep,
    service: MandateServiceDep,
    pipeline: PipelineServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    try:
        await pipeline.move(db, grant, values, context)
    except StaleVersion as error:
        raise await _stale(db, service, grant) from error
    except StageBlockedError as error:
        raise HTTPException(
            status_code=422, detail={"message": "This deal cannot leave its stage yet.", "reasons": error.reasons}
        ) from error
    return await service.read(db, grant.mandate, grant)


@router.post(
    "/{mandate_id}/close",
    response_model=MandateRead,
    summary="Close a deal as Closed won or Aborted (partner on the deal)",
    responses={**HIDDEN, 409: {"description": "Stale version"}, 422: {"description": "Outcome data missing"}},
)
async def close_mandate(
    values: MandateClose,
    grant: EditGrant,
    db: AsyncSessionDep,
    service: MandateServiceDep,
    pipeline: PipelineServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    try:
        await pipeline.close(db, grant, values, context)
    except StaleVersion as error:
        raise await _stale(db, service, grant) from error
    return await service.read(db, grant.mandate, grant)


@router.post(
    "/{mandate_id}/reopen",
    response_model=MandateRead,
    summary="Reopen a closed deal, with a reason (partner on the deal)",
    responses={**HIDDEN, 409: {"description": "Stale version"}, 422: {"description": "Reason missing or deal not closed"}},
)
async def reopen_mandate(
    values: MandateReopen,
    grant: ReopenGrant,
    db: AsyncSessionDep,
    service: MandateServiceDep,
    pipeline: PipelineServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    try:
        await pipeline.reopen(db, grant, values, context)
    except StaleVersion as error:
        raise await _stale(db, service, grant) from error
    return await service.read(db, grant.mandate, grant)


@router.get("/{mandate_id}/milestones", response_model=list[MilestoneRead], summary="Planned vs actual", responses=HIDDEN)
async def get_milestones(
    grant: ReadGrant, db: AsyncSessionDep, pipeline: PipelineServiceDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await pipeline.milestones(db, grant.mandate.id, clock.now().date())


@router.post(
    "/{mandate_id}/milestones", status_code=201, response_model=MilestoneRead, summary="Add a milestone", responses=HIDDEN
)
async def add_milestone(
    values: MilestoneCreate, grant: EditGrant, db: AsyncSessionDep, pipeline: PipelineServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await pipeline.add_milestone(db, grant, values, context)


@router.patch(
    "/{mandate_id}/milestones/{milestone_id}", response_model=MilestoneRead, summary="Edit a milestone", responses=HIDDEN
)
async def update_milestone(
    milestone_id: int,
    values: MilestoneUpdate,
    grant: EditGrant,
    db: AsyncSessionDep,
    pipeline: PipelineServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await pipeline.update_milestone(db, grant, milestone_id, values, context)


@router.delete("/{mandate_id}/milestones/{milestone_id}", status_code=204, summary="Remove a milestone", responses=HIDDEN)
async def remove_milestone(
    milestone_id: int, grant: EditGrant, db: AsyncSessionDep, pipeline: PipelineServiceDep, context: AuditContextDep
) -> Response:
    await pipeline.remove_milestone(db, grant, milestone_id, context)
    return Response(status_code=204)


criteria_router = APIRouter(tags=["Mandates"])
SettingsManagerDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]


@criteria_router.get("/", response_model=list[StageCriterionRead], summary="Stage exit criteria")
async def list_criteria(
    db: AsyncSessionDep, pipeline: PipelineServiceDep, clock: ClockDep, _: CurrentUserDep
) -> list[dict[str, Any]]:
    return await pipeline.criteria(db, clock.now())


@criteria_router.post(
    "/",
    status_code=201,
    response_model=StageCriterionRead,
    summary="Add an exit criterion to a stage (admin)",
    responses={409: {"description": "Already set"}, 422: {"description": "Unknown field, empty label or closed stage"}},
)
async def add_criterion(
    values: StageCriterionCreate,
    db: AsyncSessionDep,
    pipeline: PipelineServiceDep,
    context: AuditContextDep,
    _: SettingsManagerDep,
) -> dict[str, Any]:
    await pipeline.seed_builtin_gate(db, context.clock.now())
    return await pipeline.add_criterion(db, values, context)


@criteria_router.delete("/{criterion_id}", status_code=204, summary="Remove an exit criterion (admin)")
async def remove_criterion(
    criterion_id: int, db: AsyncSessionDep, pipeline: PipelineServiceDep, context: AuditContextDep, _: SettingsManagerDep
) -> Response:
    await pipeline.remove_criterion(db, criterion_id, context)
    return Response(status_code=204)
