from datetime import datetime

from pydantic import BaseModel


class CalendarFeedRead(BaseModel):
    url: str
    created_at: datetime
