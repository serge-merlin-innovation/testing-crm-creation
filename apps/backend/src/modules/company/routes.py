from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from .dependencies import CompanyServiceDep
from .schemas import (
    CompanyCreate,
    CompanyDetail,
    CompanyRead,
    CompanyUpdate,
    EnterpriseNumberLookup,
    FinancialYearEntry,
    FinancialYearRead,
    RegisterPrefill,
)
from .service import DuplicateCompanyError

router = APIRouter(tags=["Companies"])

Year = Annotated[int, Path(ge=1900, le=2200)]


def _duplicate_conflict(error: DuplicateCompanyError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": "A company with the same number or a similar name exists.",
            "can_confirm": not error.blocking,
            "duplicates": [duplicate.model_dump() for duplicate in error.duplicates],
        },
    )


@router.get("/", response_model=list[CompanyRead], summary="Companies by name, alphabetical")
async def list_companies(
    db: AsyncSessionDep,
    service: CompanyServiceDep,
    _: CurrentUserDep,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    return await service.search(db, q, limit)


@router.post(
    "/lookup",
    response_model=RegisterPrefill,
    summary="Pre-fill a Belgian company from the KBO/BCE register",
    description="`available: false` means the register could not answer: continue with manual entry.",
)
async def lookup_enterprise_number(
    values: EnterpriseNumberLookup, service: CompanyServiceDep, _: CurrentUserDep
) -> dict[str, Any]:
    assert values.enterprise_number is not None
    return await service.prefill(values.enterprise_number)


@router.post(
    "/",
    status_code=201,
    response_model=CompanyRead,
    summary="Create a company",
    responses={
        409: {"description": "Duplicates found; `can_confirm` true means resend with ignore_similar"},
        422: {"description": "Invalid enterprise number or missing required field"},
    },
)
async def create_company(
    values: CompanyCreate, db: AsyncSessionDep, service: CompanyServiceDep, context: AuditContextDep, _: CurrentUserDep
) -> dict[str, Any]:
    try:
        return await service.create(db, values, context)
    except DuplicateCompanyError as error:
        raise _duplicate_conflict(error) from error


@router.get("/{company_id}", response_model=CompanyDetail, summary="A company with its group tree")
async def get_company(company_id: int, db: AsyncSessionDep, service: CompanyServiceDep, _: CurrentUserDep) -> dict[str, Any]:
    return await service.detail(db, company_id)


@router.patch(
    "/{company_id}",
    response_model=CompanyRead,
    summary="Update a company, including its parent",
    responses={422: {"description": "The parent would create a loop in the group"}},
)
async def update_company(
    company_id: int,
    values: CompanyUpdate,
    db: AsyncSessionDep,
    service: CompanyServiceDep,
    context: AuditContextDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    return await service.update(db, company_id, values, context)


@router.get("/{company_id}/group-members", response_model=list[int], summary="Ids of every company in the group")
async def get_group_members(company_id: int, db: AsyncSessionDep, service: CompanyServiceDep, _: CurrentUserDep) -> list[int]:
    return sorted(await service.group_member_ids(db, company_id))


@router.get("/{company_id}/financials", response_model=list[FinancialYearRead], summary="Financials per year")
async def get_financials(
    company_id: int, db: AsyncSessionDep, service: CompanyServiceDep, _: CurrentUserDep
) -> list[dict[str, Any]]:
    return await service.financials(db, company_id)


@router.put(
    "/{company_id}/financials/{year}",
    response_model=FinancialYearRead,
    summary="Enter a year's figures (EUR thousands, or another currency with its EUR rate)",
    description="Manual figures are kept next to imported ones and win over them.",
)
async def set_financial_year(
    company_id: int,
    year: Year,
    entry: FinancialYearEntry,
    db: AsyncSessionDep,
    service: CompanyServiceDep,
    context: AuditContextDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    return await service.set_financial_year(db, company_id, year, entry, context)


@router.post(
    "/{company_id}/financials/import",
    response_model=list[FinancialYearRead],
    summary="Import the latest 3 years of filed accounts from the NBB",
)
async def import_financials(
    company_id: int, db: AsyncSessionDep, service: CompanyServiceDep, context: AuditContextDep, _: CurrentUserDep
) -> list[dict[str, Any]]:
    return await service.import_financials(db, company_id, context)
