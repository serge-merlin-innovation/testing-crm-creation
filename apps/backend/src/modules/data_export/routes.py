from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from ..security.dependencies import StepUpUserDep
from .dependencies import DataExportServiceDep
from .schemas import ApprovalDecision, ApprovalRead, ApprovalRequest, ContactFilter, ExportPreview
from .service import APPROVAL_LIMIT, ApprovalRequiredError

router = APIRouter(tags=["Exports"])

ApproverDep = Annotated[dict[str, Any], require_permission(Permission.EXPORTS_APPROVE)]
Q = Annotated[str | None, Query(max_length=200)]


@router.get("/exports/contacts/preview", response_model=ExportPreview, summary="How many rows, and whether approval is needed")
async def preview_contacts_export(
    db: AsyncSessionDep, service: DataExportServiceDep, user: CurrentUserDep, q: Q = None
) -> ExportPreview:
    rows = await service.count(db, ContactFilter(q=q))
    return ExportPreview(row_count=rows, needs_approval=service.needs_approval(user, rows), limit=APPROVAL_LIMIT)


@router.get(
    "/exports/contacts",
    summary="Export contacts as CSV; logged with user, time, filter and row count",
    description=f"An Analyst exporting more than {APPROVAL_LIMIT} contacts needs an approved request for the same filter.",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}, 403: {"description": "Partner approval required"}},
)
async def export_contacts(
    db: AsyncSessionDep,
    service: DataExportServiceDep,
    user: StepUpUserDep,
    context: AuditContextDep,
    q: Q = None,
) -> Response:
    try:
        body = await service.export_contacts(db, user, ContactFilter(q=q), context)
    except ApprovalRequiredError as error:
        raise HTTPException(
            status_code=403,
            detail=f"Exporting {error.args[0]} contacts needs a partner's approval (limit {APPROVAL_LIMIT}). "
            "Request approval first.",
        ) from error
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="contacts.csv"'},
    )


@router.post("/exports/approvals", status_code=201, response_model=ApprovalRead, summary="Ask a partner to approve an export")
async def request_export_approval(
    values: ApprovalRequest,
    db: AsyncSessionDep,
    service: DataExportServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.request_approval(db, user, values.filter, values.reason, context)


@router.get("/exports/approvals", response_model=list[ApprovalRead], summary="Export requests: mine, or all for approvers")
async def list_export_approvals(
    db: AsyncSessionDep, service: DataExportServiceDep, user: CurrentUserDep
) -> list[dict[str, Any]]:
    return await service.list(db, user)


@router.post("/exports/approvals/{approval_id}", response_model=ApprovalRead, summary="Approve or reject an export (Partner)")
async def decide_export_approval(
    approval_id: int,
    values: ApprovalDecision,
    db: AsyncSessionDep,
    service: DataExportServiceDep,
    user: ApproverDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.decide(db, user, approval_id, values.approve, context)
