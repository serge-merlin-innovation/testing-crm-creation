from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..common.exceptions import LastLeadPartnerError, MandateExistsError, TeamMemberExistsError
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import MandateServiceDep
from .policy import EditGrant, ReadGrant, TeamGrant
from .schemas import (
    DealLinkCreate,
    DealLinkRead,
    HistoryEntry,
    MandateCreate,
    MandateRead,
    MandateSummary,
    MandateUpdate,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
    UserOption,
    WallCrossingRead,
)
from .service import StaleVersionError

router = APIRouter(tags=["Mandates"])

MandateCreatorDep = Annotated[dict[str, Any], require_permission(Permission.MANDATES_CREATE)]
HIDDEN: dict[int | str, dict[str, Any]] = {
    404: {"description": "Not found, or not on the deal team (the two are indistinguishable)"}
}


@router.get(
    "/",
    response_model=list[MandateSummary],
    summary="Deals I am staffed on",
    description="Only deals on whose team you are; `q` searches code names.",
)
async def list_mandates(
    db: AsyncSessionDep, service: MandateServiceDep, user: CurrentUserDep, clock: ClockDep, q: str | None = None
) -> list[dict[str, Any]]:
    return await service.list_visible(db, user, clock.now(), q)


@router.get("/lead-partners", response_model=list[UserOption], summary="Users who can lead a mandate")
async def list_lead_partners(db: AsyncSessionDep, service: MandateServiceDep, _: MandateCreatorDep) -> list[dict[str, Any]]:
    return await service.lead_partners(db)


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
