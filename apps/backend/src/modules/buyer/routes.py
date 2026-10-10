from typing import Any

from fastapi import APIRouter, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..mandate.policy import EditGrant, ExportGrant, ReadGrant
from .dependencies import BuyerServiceDep, InvestorProfileServiceDep
from .schemas import (
    BuyerGrid,
    BuyerRead,
    BuyersAdd,
    BuyersAdded,
    BuyerUpdate,
    CompanyRef,
    ContactBuyerRole,
    ExclusionRead,
    InvestorProfileRead,
    InvestorProfileUpdate,
    NdaRead,
    NdaUpdate,
    StatusChange,
    Suggestion,
)

# Under /mandates: the deal's buyer list.
router = APIRouter(tags=["Buyers"])
# Under /companies: investor profiles and the client's exclusion list.
companies_router = APIRouter(tags=["Buyers"])
# Under /contacts.
contacts_router = APIRouter(tags=["Buyers"])

HIDDEN: dict[int | str, dict[str, Any]] = {404: {"description": "Not found, or not visible to you"}}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@companies_router.get(
    "/{company_id}/investor-profile",
    response_model=InvestorProfileRead,
    summary="A buyer's investment criteria, portfolio, past declines and NDA restrictions",
    description="Declines list only closed deals the caller can read. `outdated` flags criteria unchanged for 12 months.",
)
async def get_profile(
    company_id: int, db: AsyncSessionDep, service: InvestorProfileServiceDep, user: CurrentUserDep, clock: ClockDep
) -> dict[str, Any]:
    return await service.read(db, company_id, user, clock.now())


@companies_router.put(
    "/{company_id}/investor-profile",
    response_model=InvestorProfileRead,
    summary="Set a buyer's investment criteria (CO-04)",
    description="Ticket size in EUR millions.",
)
async def put_profile(
    company_id: int,
    values: InvestorProfileUpdate,
    db: AsyncSessionDep,
    service: InvestorProfileServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.update(db, company_id, values, user, context)


@companies_router.post(
    "/{company_id}/portfolio",
    response_model=InvestorProfileRead,
    summary="Link a portfolio company to a PE fund",
    description="The portfolio company joins the fund's group as a subsidiary.",
)
async def link_portfolio(
    company_id: int,
    values: CompanyRef,
    db: AsyncSessionDep,
    service: InvestorProfileServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.link_portfolio(db, company_id, values.company_id, user, context)


@companies_router.get("/{company_id}/exclusions", response_model=list[ExclusionRead], summary="The client's exclusion list")
async def get_exclusions(
    company_id: int, db: AsyncSessionDep, service: InvestorProfileServiceDep, user: CurrentUserDep, clock: ClockDep
) -> list[dict[str, Any]]:
    await service.client_grants(db, user, company_id, clock.now())
    return await service.exclusions(db, company_id)


@companies_router.post(
    "/{company_id}/exclusions",
    status_code=201,
    response_model=ExclusionRead,
    summary="Add a company the client does not want approached",
)
async def add_exclusion(
    company_id: int,
    values: CompanyRef,
    db: AsyncSessionDep,
    service: InvestorProfileServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    await service.require_exclusion_manager(db, user, company_id, context.clock.now())
    return await service.add_exclusion(db, company_id, values.company_id, context)


@companies_router.delete("/{company_id}/exclusions/{excluded_id}", status_code=204, summary="Remove from the exclusion list")
async def remove_exclusion(
    company_id: int,
    excluded_id: int,
    db: AsyncSessionDep,
    service: InvestorProfileServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> Response:
    await service.require_exclusion_manager(db, user, company_id, context.clock.now())
    await service.remove_exclusion(db, company_id, excluded_id, context)
    return Response(status_code=204)


@contacts_router.get(
    "/{contact_id}/buyer-roles",
    response_model=list[ContactBuyerRole],
    summary="Where a contact is a buyer",
    description="Only deals the caller is staffed on (AUTHZ-02 c5).",
)
async def contact_buyer_roles(
    contact_id: int, db: AsyncSessionDep, service: InvestorProfileServiceDep, user: CurrentUserDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await service.buyer_roles(db, contact_id, user, clock.now())


@router.get("/{mandate_id}/buyers", response_model=BuyerGrid, summary="The buyer grid with funnel counts", responses=HIDDEN)
async def get_buyers(grant: ReadGrant, db: AsyncSessionDep, service: BuyerServiceDep) -> dict[str, Any]:
    return await service.grid(db, grant)


@router.get(
    "/{mandate_id}/buyers/suggestions",
    response_model=list[Suggestion],
    summary="Suggest buyers",
    description="Investor profiles ranked by fit with the target's sector, geography and size (BUY-01).",
    responses=HIDDEN,
)
async def get_suggestions(grant: ReadGrant, db: AsyncSessionDep, service: BuyerServiceDep) -> list[dict[str, Any]]:
    return await service.suggestions(db, grant)


@router.post(
    "/{mandate_id}/buyers",
    response_model=BuyersAdded,
    summary="Add buyers to the list in bulk",
    description="Already listed buyers are skipped. Conflicts and client exclusions come back as warnings and are added "
    "only with `confirm: true`. A Do not contact contact is refused.",
    responses=HIDDEN,
)
async def add_buyers(
    values: BuyersAdd, grant: EditGrant, db: AsyncSessionDep, service: BuyerServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.add(db, grant, values, context)


@router.get(
    "/{mandate_id}/buyers/export",
    summary="Export the buyer list for client approval (Excel)",
    description="Buyer, type, rationale and contact. Internal notes are never exported.",
    responses={**HIDDEN, 200: {"content": {XLSX: {}}}},
)
async def export_buyers(grant: ExportGrant, db: AsyncSessionDep, service: BuyerServiceDep, context: AuditContextDep) -> Response:
    content = await service.export(db, grant, context)
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{grant.mandate.code_name}-buyers.xlsx"'},
    )


@router.post(
    "/{mandate_id}/buyers/status",
    response_model=BuyerGrid,
    summary="Change the status of one or many buyers",
    description="Every selected buyer gets the same date. Declined needs a reason; IM sent and later need a signed NDA.",
    responses=HIDDEN,
)
async def set_status(
    values: StatusChange, grant: EditGrant, db: AsyncSessionDep, service: BuyerServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.set_status(db, grant, values, context)


@router.patch(
    "/{mandate_id}/buyers/{buyer_id}",
    response_model=BuyerRead,
    summary="Edit a buyer, or record the client's Approved / Excluded",
    responses=HIDDEN,
)
async def update_buyer(
    buyer_id: int,
    values: BuyerUpdate,
    grant: EditGrant,
    db: AsyncSessionDep,
    service: BuyerServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.update(db, grant, buyer_id, values, context)


@router.put(
    "/{mandate_id}/buyers/{buyer_id}/nda",
    response_model=NdaRead,
    summary="Log the NDA's dates and link",
    description="The buyer moves to NDA signed only when the signed date is set.",
    responses=HIDDEN,
)
async def put_nda(
    buyer_id: int,
    values: NdaUpdate,
    grant: EditGrant,
    db: AsyncSessionDep,
    service: BuyerServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.set_nda(db, grant, buyer_id, values, context)
