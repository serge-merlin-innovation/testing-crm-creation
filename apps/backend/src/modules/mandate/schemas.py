from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .stages import DealStage


class MandateType(StrEnum):
    SELL_SIDE = "sell_side"
    BUY_SIDE = "buy_side"
    FUNDRAISING = "fundraising"
    DEBT_ADVISORY = "debt_advisory"


class TeamRole(StrEnum):
    LEAD_PARTNER = "lead_partner"
    PARTNER = "partner"
    DIRECTOR = "director"
    ANALYST = "analyst"
    OTHER = "other"


CodeName = Annotated[str, Field(min_length=2, max_length=100, examples=["Falcon"])]
EnterpriseValue = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2, description="EUR thousands")]


class MandateCreate(BaseModel):
    code_name: CodeName
    client_id: int
    type: MandateType
    sector_id: int
    lead_partner_id: int
    estimated_ev: EnterpriseValue
    target_id: int | None = None


class MandateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(description="The version you read; a stale one is refused with 409")]
    code_name: CodeName | None = None
    client_id: int | None = None
    target_id: int | None = None
    type: MandateType | None = None
    sector_id: int | None = None
    estimated_ev: EnterpriseValue | None = None


class MandateSummary(BaseModel):
    id: int
    code_name: str
    type: MandateType
    stage: DealStage
    lead_partner_id: int


class MandateRead(MandateSummary):
    client_id: int
    client_name: str
    target_id: int | None
    target_name: str | None
    sector_id: int
    estimated_ev: Decimal
    lead_partner_name: str
    stages: list[DealStage]
    version: int
    created_at: datetime
    updated_at: datetime
    can_edit: bool
    can_manage_team: bool


class TeamMemberCreate(BaseModel):
    user_id: int
    role: TeamRole
    expires_at: datetime | None = None


class TeamMemberRead(BaseModel):
    user_id: int
    name: str
    email: str
    role: TeamRole
    added_by: int
    added_by_name: str
    added_at: datetime
    expires_at: datetime | None


class TeamRead(BaseModel):
    can_manage: bool
    members: list[TeamMemberRead]


class UserOption(BaseModel):
    id: int
    name: str
    email: str
    role_name: str | None


class WallCrossingRead(BaseModel):
    action: str
    user_id: int
    user_name: str
    by_user_id: int
    by_user_name: str
    role: TeamRole
    at: datetime
    expires_at: datetime | None


class HistoryEntry(BaseModel):
    action: str
    at: datetime
    user_id: int | None
    user_name: str | None
    field: str | None
    old_value: str | None
    new_value: str | None


def _https(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Only https links are accepted")
    return value


class DealLinkCreate(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=50, examples=["VDR"])]
    url: Annotated[str, Field(max_length=2000, examples=["https://vdr.example.com/rooms/falcon"]), AfterValidator(_https)]


class DealLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    url: str
    added_by: int
    added_at: datetime
