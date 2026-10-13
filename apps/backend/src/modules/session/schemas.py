from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SessionPolicyValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desktop_idle_minutes: int = Field(ge=5, le=120)
    mobile_idle_minutes: int = Field(ge=5, le=120)
    absolute_hours: int = Field(ge=1, le=24)
    mobile_read_only: bool

    @model_validator(mode="after")
    def mobile_not_longer_than_desktop(self) -> "SessionPolicyValues":
        if self.mobile_idle_minutes > self.desktop_idle_minutes:
            raise ValueError("The mobile timeout cannot be longer than the desktop timeout.")
        return self


class SessionStatus(BaseModel):
    idle_expires_at: datetime
    absolute_expires_at: datetime | None
    warning_seconds: int
    mobile: bool
    mobile_read_only: bool


class SessionsRevoked(BaseModel):
    revoked: int
