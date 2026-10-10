from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Channel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    BOTH = "both"
    NONE = "none"


class EventKind(StrEnum):
    """Every event a user can tune. A new notifying feature adds its kind here."""

    DEAL_TEAM_ADDED = "deal_team.added"
    TASK_ASSIGNED = "task.assigned"
    TASK_OVERDUE_DIGEST = "task.overdue_digest"
    MILESTONE_DUE = "milestone.due"
    CONFLICT_REVIEW_OVERDUE = "conflict.review_overdue"
    ACCESS_REQUESTED = "access.requested"
    ACCESS_APPROVED = "access.approved"
    ACCESS_REJECTED = "access.rejected"
    BREAK_GLASS = "access.break_glass"
    ACCESS_REVIEW_OVERDUE = "access.review_overdue"


DEFAULT_CHANNEL = Channel.BOTH


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


class PreferenceRead(BaseModel):
    kind: EventKind
    channel: Channel


class PreferencesUpdate(BaseModel):
    preferences: dict[EventKind, Channel]
