from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SecondFactorRequired(BaseModel):
    step: Literal["code", "enrol"]
    challenge: str
    otpauth_uri: str | None = None
    qr_svg: str | None = None


class LoginCompleted(BaseModel):
    step: Literal["done"] = "done"
    csrf_token: str
    recovery_codes: list[str] | None = None


class SecondFactorSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge: str
    code: str = Field(min_length=6, max_length=16)
    trust_device: bool = False


class TravelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    travel_from: date | None = None
    travel_until: date | None = None

    @model_validator(mode="after")
    def both_or_neither(self) -> "TravelUpdate":
        if (self.travel_from is None) != (self.travel_until is None):
            raise ValueError("Set both dates or neither")
        if self.travel_from and self.travel_until and self.travel_from > self.travel_until:
            raise ValueError("The range ends before it starts")
        return self


class SecurityProfile(BaseModel):
    user_id: int
    two_factor_enabled: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    last_login_ip: str | None
    last_login_device: str | None
    travel_from: date | None
    travel_until: date | None
    travelling: bool


class SecurityPolicyRead(BaseModel):
    trusted_devices_enabled: bool


class SecurityPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trusted_devices_enabled: bool
