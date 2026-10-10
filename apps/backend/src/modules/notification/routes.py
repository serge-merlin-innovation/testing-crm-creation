from typing import Any

from fastapi import APIRouter

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..audit.service import AuditService
from ..mandate.policy import DealPolicy
from .dependencies import NotificationServiceDep
from .schemas import NotificationRead, PreferenceRead, PreferencesUpdate

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


@router.get("/preferences", response_model=list[PreferenceRead], summary="My channel per notification event type")
async def get_preferences(db: AsyncSessionDep, service: NotificationServiceDep, user: CurrentUserDep) -> list[Any]:
    return await service.preferences(db, user["id"])


@router.put(
    "/preferences",
    response_model=list[PreferenceRead],
    summary="Choose in-app, email, both or none per event type",
    description="Only the event types sent are changed.",
)
async def set_preferences(
    values: PreferencesUpdate,
    db: AsyncSessionDep,
    service: NotificationServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> list[Any]:
    AuditService().record(
        db,
        context,
        "notification_preferences.updated",
        record_type="notification_preferences",
        record_id=user["id"],
        new_values={kind.value: channel.value for kind, channel in values.preferences.items()},
    )
    return await service.set_preferences(db, user["id"], values.preferences)
