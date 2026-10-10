from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import FeeGrant, FeeServiceDep, InvoiceGrant
from .schemas import FeeTermsRead, FeeTermsValues, InvoiceCreate, InvoiceRead, InvoiceUpdate

router = APIRouter(tags=["Fees"])
deal_router = APIRouter(tags=["Fees"])

FeeReaderDep = Annotated[dict[str, Any], require_permission(Permission.FEES_READ)]
HIDDEN: dict[int | str, dict[str, Any]] = {
    403: {"description": "Fee fields are hidden from your role"},
    404: {"description": "Not found, or a deal you may not read"},
}


@router.get(
    "/",
    response_model=list[FeeTermsRead],
    summary="Fee terms of the deals I may read (fees.read)",
    description="Back-office sees every deal's fees. `min_expected_fee` (EUR) filters; it is offered only to fee readers.",
)
async def list_fees(
    db: AsyncSessionDep,
    service: FeeServiceDep,
    user: FeeReaderDep,
    clock: ClockDep,
    min_expected_fee: Decimal | None = None,
) -> list[dict[str, Any]]:
    return await service.list_visible(db, user, clock.now(), min_expected_fee)


@router.get("/export", summary="Export fee terms as CSV (fees.read); the export is audited", response_class=Response)
async def export_fees(
    db: AsyncSessionDep,
    service: FeeServiceDep,
    user: FeeReaderDep,
    clock: ClockDep,
    context: AuditContextDep,
    min_expected_fee: Decimal | None = None,
) -> Response:
    rows = await service.list_visible(db, user, clock.now(), min_expected_fee)
    body = service.export_csv(rows, context, db, {"min_expected_fee": str(min_expected_fee) if min_expected_fee else None})
    await db.commit()
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="fees.csv"'},
    )


@deal_router.get(
    "/{mandate_id}/fees", response_model=FeeTermsRead, summary="A deal's fee terms and expected fee", responses=HIDDEN
)
async def get_fees(grant: FeeGrant, db: AsyncSessionDep, service: FeeServiceDep) -> dict[str, Any]:
    return await service.read(db, grant)


@deal_router.put(
    "/{mandate_id}/fees",
    response_model=FeeTermsRead,
    summary="Set a deal's fee terms (back-office, or a partner on the deal)",
    description="After the engagement letter is linked, a change needs `change_reason` and `amended_letter_url`.",
    responses={**HIDDEN, 422: {"description": "Invalid terms, or a post-engagement change without reason or letter"}},
)
async def put_fees(
    values: FeeTermsValues, grant: FeeGrant, db: AsyncSessionDep, service: FeeServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.save(db, grant, values, context)


@deal_router.get("/{mandate_id}/invoices", response_model=list[InvoiceRead], summary="Invoices on a deal", responses=HIDDEN)
async def list_invoices(grant: FeeGrant, db: AsyncSessionDep, service: FeeServiceDep) -> list[Any]:
    return await service.invoices(db, grant.mandate.id)


@deal_router.post(
    "/{mandate_id}/invoices",
    status_code=201,
    response_model=InvoiceRead,
    summary="Record an invoice (back-office)",
    description="A success-fee invoice completes the invoice task raised at closing.",
    responses=HIDDEN,
)
async def record_invoice(
    values: InvoiceCreate, grant: InvoiceGrant, db: AsyncSessionDep, service: FeeServiceDep, context: AuditContextDep
) -> Any:
    return await service.record_invoice(db, grant, values, context)


@deal_router.patch(
    "/{mandate_id}/invoices/{invoice_id}",
    response_model=InvoiceRead,
    summary="Mark an invoice paid (back-office)",
    responses=HIDDEN,
)
async def update_invoice(
    invoice_id: int,
    values: InvoiceUpdate,
    grant: InvoiceGrant,
    db: AsyncSessionDep,
    service: FeeServiceDep,
    context: AuditContextDep,
) -> Any:
    return await service.update_invoice(db, grant, invoice_id, values, context)
