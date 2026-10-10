from typing import Annotated, Any

from fastapi import APIRouter, HTTPException

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..common.exceptions import MergeBlockedError, UndoWindowClosedError
from ..role.authorization import require_permission
from .dependencies import MergeServiceDep
from .schemas import MergeRead, MergeRequest
from .service import UNDO_PERMISSION

router = APIRouter(tags=["Merge"])

UndoerDep = Annotated[dict[str, Any], require_permission(UNDO_PERMISSION)]


@router.post(
    "/",
    status_code=201,
    response_model=MergeRead,
    summary="Merge a duplicate contact or company into the survivor",
    description=(
        "`fields` picks, per field, whose value the survivor keeps. Activities, notes, tasks, deals, roles, "
        "relationship holders and links move to the survivor; the duplicate is deleted. Audited. 403 when either "
        "record is on a deal the caller cannot access: Compliance must merge those."
    ),
    responses={403: {"description": "A record is on a deal the caller cannot access"}},
)
async def merge_records(
    values: MergeRequest, db: AsyncSessionDep, service: MergeServiceDep, user: CurrentUserDep, context: AuditContextDep
) -> dict[str, Any]:
    try:
        return await service.merge(db, user, values, context)
    except MergeBlockedError as error:
        raise HTTPException(
            status_code=403, detail="One of these records is on a deal you cannot access. Ask Compliance to merge them."
        ) from error


@router.get("/", response_model=list[MergeRead], summary="Admin: merges of the last 30 days, undoable")
async def list_merges(db: AsyncSessionDep, service: MergeServiceDep, _: UndoerDep, clock: ClockDep) -> list[Any]:
    return await service.recent(db, clock.now())


@router.post(
    "/{merge_id}/undo",
    response_model=MergeRead,
    summary="Admin: undo a merge done in the last 30 days",
    responses={409: {"description": "Older than 30 days, or already undone"}},
)
async def undo_merge(
    merge_id: int, db: AsyncSessionDep, service: MergeServiceDep, _: UndoerDep, context: AuditContextDep
) -> dict[str, Any]:
    try:
        return await service.undo(db, merge_id, context)
    except UndoWindowClosedError as error:
        raise HTTPException(
            status_code=409, detail="This merge was done more than 30 days ago, or was already undone."
        ) from error
