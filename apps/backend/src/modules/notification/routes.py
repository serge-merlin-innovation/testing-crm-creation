from typing import Any

from fastapi import APIRouter

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..mandate.policy import DealPolicy
from .dependencies import NotificationServiceDep
from .schemas import NotificationRead

router = APIRouter(tags=["Notifications"])


@router.get(
    "/",
    response_model=list[NotificationRead],
    summary="My in-app notifications",
    description="Deal notifications disappear once you are no longer on that deal's team.",
)
async def list_notifications(
    db: AsyncSessionDep, service: NotificationServiceDep, user: CurrentUserDep, clock: ClockDep
) -> list[Any]:
    visible = await DealPolicy(clock.now()).visible_mandate_ids(db, user)
    return await service.list_for(db, user["id"], visible)
