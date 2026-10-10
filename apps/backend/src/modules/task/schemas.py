from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from ..activity.schemas import RecordType


class Recurrence(StrEnum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TaskCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200, examples=["Weekly client update"])]
    assignee_id: int
    due_date: date
    record_type: RecordType | None = None
    record_id: int | None = None
    recurrence: Recurrence = Recurrence.NONE


class TaskRead(BaseModel):
    id: int
    title: str
    assignee_id: int
    created_by: int
    due_date: date
    recurrence: Recurrence
    record_type: RecordType | None
    record_id: int | None
    mandate_id: int | None
    completed_at: datetime | None
    overdue: bool


class DealTaskRead(TaskRead):
    assignee_name: str
