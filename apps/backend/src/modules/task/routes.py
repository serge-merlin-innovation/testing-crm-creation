from typing import Any

from fastapi import APIRouter

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from .dependencies import TaskServiceDep
from .schemas import TaskCreate, TaskRead

router = APIRouter(tags=["Tasks"])


@router.post(
    "/",
    status_code=201,
    response_model=TaskRead,
    summary="Assign a task",
    description="The assignee is notified. A task on a deal can only go to that deal's team (422 on `assignee_id`).",
)
async def create_task(
    values: TaskCreate,
    db: AsyncSessionDep,
    service: TaskServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.create(db, user, values, clock.now(), context)


@router.get("/mine", response_model=list[TaskRead], summary="My tasks, soonest due first")
async def my_tasks(
    db: AsyncSessionDep, service: TaskServiceDep, user: CurrentUserDep, clock: ClockDep, include_done: bool = False
) -> list[dict[str, Any]]:
    return await service.mine(db, user, clock.now(), include_done)


@router.post(
    "/{task_id}/complete",
    response_model=TaskRead,
    summary="Complete a task",
    description="A recurring task creates its next occurrence.",
)
async def complete_task(
    task_id: int,
    db: AsyncSessionDep,
    service: TaskServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.complete(db, user, task_id, clock.now(), context)
