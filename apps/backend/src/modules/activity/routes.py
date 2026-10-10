from typing import Annotated, Any

from fastapi import APIRouter, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from .dependencies import ActivityServiceDep, NoteServiceDep
from .schemas import (
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
    NoteCreate,
    NoteRead,
    RecordRef,
    RecordType,
    TimelineRead,
)
from .service import RESTORE_PERMISSION, timeline

router = APIRouter(tags=["Activities"])
notes_router = APIRouter(tags=["Notes"])
timeline_router = APIRouter(tags=["Timeline"])

RestorerDep = Annotated[dict[str, Any], require_permission(RESTORE_PERMISSION)]


@router.post(
    "/",
    status_code=201,
    response_model=ActivityRead,
    summary="Log a call, meeting or email against one or more records",
    description="Shows on every linked record's timeline. Linking a deal needs edit access to it.",
)
async def log_activity(
    values: ActivityCreate,
    db: AsyncSessionDep,
    service: ActivityServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.create(db, user, values, clock.now(), context)


@router.get("/deleted", summary="Admin: activities deleted in the last 30 days, restorable")
async def list_deleted(db: AsyncSessionDep, service: ActivityServiceDep, _: RestorerDep, clock: ClockDep) -> list[Any]:
    return await service.deleted(db, clock.now())


@router.patch(
    "/{activity_id}",
    response_model=ActivityRead,
    summary="Edit an activity",
    description="An edit more than 7 days after logging is shown with `edited_at`.",
)
async def edit_activity(
    activity_id: int,
    values: ActivityUpdate,
    db: AsyncSessionDep,
    service: ActivityServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.update(db, user, activity_id, values, clock.now(), context)


@router.delete("/{activity_id}", status_code=204, summary="Soft-delete an activity (author or admin)")
async def delete_activity(
    activity_id: int,
    db: AsyncSessionDep,
    service: ActivityServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> Response:
    await service.delete(db, user, activity_id, clock.now(), context)
    return Response(status_code=204)


@router.post(
    "/{activity_id}/restore",
    status_code=204,
    summary="Admin: restore an activity deleted in the last 30 days",
    responses={409: {"description": "Deleted more than 30 days ago"}},
)
async def restore_activity(
    activity_id: int,
    db: AsyncSessionDep,
    service: ActivityServiceDep,
    _: RestorerDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> Response:
    await service.restore(db, activity_id, clock.now(), context)
    return Response(status_code=204)


@notes_router.post(
    "/",
    status_code=201,
    response_model=NoteRead,
    summary="Add a shared, private or deal-confidential note to a record",
    description="Private: only the author, admins included. Deal-confidential: only the deal team of `mandate_id`.",
)
async def add_note(
    values: NoteCreate,
    db: AsyncSessionDep,
    service: NoteServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> Any:
    return await service.create(db, user, values, clock.now(), context)


@timeline_router.get(
    "/{record_type}/{record_id}",
    response_model=TimelineRead,
    summary="A record's activities, notes and (for a company) its deals",
    description="Deal-linked items appear only to the deal team; private notes only to their author.",
)
async def get_timeline(
    record_type: RecordType, record_id: int, db: AsyncSessionDep, user: CurrentUserDep, clock: ClockDep
) -> dict[str, Any]:
    return await timeline(db, user, RecordRef(record_type=record_type, record_id=record_id), clock.now())
