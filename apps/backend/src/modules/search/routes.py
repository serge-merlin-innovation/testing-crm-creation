from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..company.schemas import CompanyType
from .dependencies import SavedFilterServiceDep, SearchServiceDep
from .schemas import SavedFilterCreate, SavedFilterRead, SearchCriteria, SearchResults, ShareUpdate

router = APIRouter(tags=["Search"])
filters_router = APIRouter(tags=["Search"])


@router.get(
    "/",
    response_model=SearchResults,
    summary="Global search across companies, contacts and deals, grouped by type",
    description=(
        "At least 3 characters (or a criterion). Accent-, case- and typo-tolerant. Deals match on code name only "
        "and only deals the caller is staffed on appear. `filter_id` applies a saved filter; query parameters add to it."
    ),
)
async def global_search(
    db: AsyncSessionDep,
    service: SearchServiceDep,
    filters: SavedFilterServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    filter_id: int | None = None,
    company_type: Annotated[list[CompanyType] | None, Query()] = None,
    country_id: Annotated[list[int] | None, Query()] = None,
    sector_id: Annotated[list[int] | None, Query()] = None,
    ev_min: Decimal | None = None,
    ev_max: Decimal | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    base = SearchCriteria()
    if filter_id is not None:
        base = SearchCriteria.model_validate((await filters.get(db, user, filter_id)).criteria)
    criteria = base.model_copy(
        update={
            key: value
            for key, value in {
                "q": q,
                "company_types": company_type,
                "country_ids": country_id,
                "sector_ids": sector_id,
                "ev_min": ev_min,
                "ev_max": ev_max,
            }.items()
            if value
        }
    )
    return await service.search(db, user, criteria, clock.now(), limit)


@filters_router.get("/", response_model=list[SavedFilterRead], summary="My saved filters and those shared with everyone")
async def list_saved_filters(db: AsyncSessionDep, filters: SavedFilterServiceDep, user: CurrentUserDep) -> list[Any]:
    return await filters.visible(db, user)


@filters_router.post("/", status_code=201, response_model=SavedFilterRead, summary="Save a search filter")
async def create_saved_filter(
    values: SavedFilterCreate,
    db: AsyncSessionDep,
    filters: SavedFilterServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await filters.create(db, user, values, clock.now(), context)


@filters_router.put("/{filter_id}/shared", response_model=SavedFilterRead, summary="Share or unshare my saved filter")
async def share_saved_filter(
    filter_id: int,
    values: ShareUpdate,
    db: AsyncSessionDep,
    filters: SavedFilterServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await filters.set_shared(db, user, filter_id, values.shared, context)


@filters_router.delete("/{filter_id}", status_code=204, summary="Delete my saved filter")
async def delete_saved_filter(
    filter_id: int, db: AsyncSessionDep, filters: SavedFilterServiceDep, user: CurrentUserDep, context: AuditContextDep
) -> Response:
    await filters.delete(db, user, filter_id, context)
    return Response(status_code=204)
