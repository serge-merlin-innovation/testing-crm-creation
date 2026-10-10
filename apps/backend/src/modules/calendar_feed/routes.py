from typing import Any

from fastapi import APIRouter, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..role.authorization import RequireRecordAccess
from .dependencies import CalendarFeedServiceDep
from .schemas import CalendarFeedRead

router = APIRouter(tags=["Calendar feed"])


def _read(service: Any, feed: Any) -> dict[str, Any]:
    return {"url": service.url(feed.token), "created_at": feed.created_at}


@router.get(
    "/",
    dependencies=[RequireRecordAccess],
    response_model=CalendarFeedRead,
    summary="My private iCal feed URL",
    description="Subscribe to it in any calendar app: my meetings, open tasks and my deals' milestones.",
)
async def my_feed(
    db: AsyncSessionDep, service: CalendarFeedServiceDep, user: CurrentUserDep, clock: ClockDep
) -> dict[str, Any]:
    return _read(service, await service.get_or_create(db, user, clock.now()))


@router.post(
    "/regenerate",
    dependencies=[RequireRecordAccess],
    response_model=CalendarFeedRead,
    summary="Replace my feed URL; the old one stops working at once",
)
async def regenerate_feed(
    db: AsyncSessionDep, service: CalendarFeedServiceDep, user: CurrentUserDep, clock: ClockDep
) -> dict[str, Any]:
    return _read(service, await service.regenerate(db, user, clock.now()))


@router.get(
    "/ics/{token}.ics",
    summary="The iCal feed itself (the URL is the credential)",
    description="Deal events show the deal code name only. An unknown or replaced token is 404.",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}, 404: {"description": "Unknown feed"}},
)
async def feed_ics(token: str, db: AsyncSessionDep, service: CalendarFeedServiceDep, clock: ClockDep) -> Response:
    body = await service.render(db, token, clock.now())
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )
