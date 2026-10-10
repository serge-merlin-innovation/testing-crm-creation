from datetime import date, datetime
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


class ConflictStatus(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    CLEARED = "cleared"
    REJECTED = "rejected"


# Deals in these states are seen only by their creator and compliance (DEAL-01 c4).
HIDDEN_CONFLICT_STATUSES = (ConflictStatus.REVIEW.value, ConflictStatus.REJECTED.value)


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
    counterparty_ids: Annotated[
        list[int], Field(max_length=50, description="Known counterparties, checked for conflicts with the client and target")
    ] = []


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
    stage_changed_at: datetime | None
    closed_at: datetime | None
    outcome: "OutcomeRead"
    can_edit: bool
    can_manage_team: bool
    can_close: bool
    can_reopen: bool
    conflict_status: ConflictStatus
    frozen: bool


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


class MandateListItem(MandateSummary):
    sector_id: int
    estimated_ev: Decimal
    lead_partner_name: str
    stage_changed_at: datetime | None
    closed_at: datetime | None


class DealFilters(BaseModel):
    partner_id: int | None = None
    type: MandateType | None = None
    sector_id: int | None = None
    stage: DealStage | None = None


class StageMove(BaseModel):
    version: int
    stage: DealStage
    reason: Annotated[str | None, Field(max_length=1000, description="Required when moving backwards")] = None


class Outcome(StrEnum):
    CLOSED_WON = "closed_won"
    ABORTED = "aborted"


class MandateClose(BaseModel):
    version: int
    outcome: Outcome
    final_ev: EnterpriseValue | None = None
    buyer: Annotated[str | None, Field(max_length=200)] = None
    ev_ebitda: Annotated[Decimal | None, Field(ge=0, max_digits=8, decimal_places=2, description="EV / EBITDA")] = None
    closing_date: date | None = None
    tombstone_allowed: bool | None = None
    abort_reason: Annotated[str | None, Field(max_length=1000)] = None


class MandateReopen(BaseModel):
    version: int
    reason: Annotated[str | None, Field(max_length=1000)] = None


class OutcomeRead(BaseModel):
    final_ev: Decimal | None
    buyer: str | None
    ev_ebitda: Decimal | None
    closing_date: date | None
    tombstone_allowed: bool | None
    abort_reason: str | None


class CriterionKind(StrEnum):
    FIELD = "field"
    LINK_LABEL = "link_label"
    KYC_ENGAGEMENT = "kyc_engagement"


class StageCriterionCreate(BaseModel):
    stage: DealStage
    kind: CriterionKind
    value: Annotated[str | None, Field(max_length=100, description="Field name or link label")] = None


class StageCriterionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: DealStage
    kind: CriterionKind
    value: str | None
    description: str


class MilestoneCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100, examples=["IM sent"])]
    planned_date: date
    actual_date: date | None = None


class MilestoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    planned_date: date | None = None
    actual_date: date | None = None


class MilestoneRead(BaseModel):
    id: int
    name: str
    planned_date: date
    actual_date: date | None
    late: bool
    days_late: int


MandateRead.model_rebuild()
