from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastcrud import PaginatedListResponse, compute_offset, paginated_response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import AuditServiceDep
from .scope import readable_rows
from .schemas import AuditEntryRead

router = APIRouter(tags=["Audit log"])


@router.get(
    "/",
    response_model=PaginatedListResponse[AuditEntryRead],
    summary="Search the audit log",
    description="Read-only. The audit log is append-only: there is no endpoint that edits or deletes an entry.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Requires audit.read"}},
)
async def search_audit_log(
    db: AsyncSessionDep,
    audit_service: AuditServiceDep,
    reader: Annotated[dict, require_permission(Permission.AUDIT_READ)],
    clock: ClockDep,
    user_id: int | None = None,
    record_type: str | None = None,
    record_id: str | None = None,
    action: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict[str, Any]:
    result = await audit_service.search(
        db,
        user_id=user_id,
        record_type=record_type,
        record_id=record_id,
        action=action,
        scope=await readable_rows(db, reader, clock.now()),
        offset=compute_offset(page, items_per_page),
        limit=items_per_page,
    )
    data = [AuditEntryRead.model_validate(entry, from_attributes=True).model_dump() for entry in result["data"]]
    return paginated_response(
        crud_data={"data": data, "total_count": result["total_count"]}, page=page, items_per_page=items_per_page
    )
