from typing import Annotated

from fastapi import Depends

from .service import CalendarFeedService


def get_calendar_feed_service() -> CalendarFeedService:
    return CalendarFeedService()


CalendarFeedServiceDep = Annotated[CalendarFeedService, Depends(get_calendar_feed_service)]
