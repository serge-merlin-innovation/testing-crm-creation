from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from ..common.validators import https_url
from ..fee.schemas import FeeTermsValues
from ..mandate.schemas import CodeName, EnterpriseValue, MandateType


class OpportunityStage(StrEnum):
    LEAD = "lead"
    CONTACTED = "contacted"
    MEETING_HELD = "meeting_held"
    PITCH = "pitch"
    ENGAGEMENT_LETTER_SENT = "engagement_letter_sent"
    WON = "won"
    LOST = "lost"
    ON_HOLD = "on_hold"


# Won and Lost end the opportunity; On hold parks it until the revisit date.
CLOSED_STAGES = frozenset({OpportunityStage.WON.value, OpportunityStage.LOST.value})


class Trigger(StrEnum):
    SUCCESSION = "succession"
    GROWTH = "growth"
    CARVE_OUT = "carve_out"
    DISTRESS = "distress"


class LostReason(StrEnum):
    FEE = "fee"
    COMPETITOR = "competitor"
    TIMING = "timing"
    CLIENT_DECIDED_NOT_TO_SELL = "client_decided_not_to_sell"


class OpportunityCreate(BaseModel):
    company_id: int
    type: MandateType
    trigger: Trigger
    estimated_ev: EnterpriseValue
    probability: Annotated[int, Field(ge=0, le=100, description="Percent")]
    sector_id: int | None = None


class StageChange(BaseModel):
    stage: OpportunityStage
    lost_reason: LostReason | None = None
    competitor_advisor: Annotated[str | None, Field(max_length=200)] = None
    revisit_date: date | None = None


class MemberCreate(BaseModel):
    user_id: int


class LinkCreate(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=50, examples=["Pitch deck"])]
    url: Annotated[str, Field(max_length=2000, examples=["https://files.example.com/pitch.pptx"]), AfterValidator(https_url)]


class CredentialCreate(BaseModel):
    mandate_id: int


class WinRequest(BaseModel):
    code_name: CodeName
    sector_id: Annotated[int | None, Field(description="Defaults to the opportunity's sector")] = None
    target_id: int | None = None


class MemberRead(BaseModel):
    user_id: int
    name: str
    role_name: str | None


class LinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    url: str
    added_by: int
    added_at: datetime


class CredentialRead(BaseModel):
    id: int
    code_name: str
    type: str
    sector_id: int
    ev: Annotated[Decimal | None, Field(description="Final EV in EUR thousands")]
    closing_date: date | None


class OpportunityListItem(BaseModel):
    id: int
    company_id: int
    company_name: str
    owner_id: int
    owner_name: str
    type: MandateType
    trigger: Trigger
    estimated_ev: Decimal
    probability: int
    sector_id: int | None
    stage: OpportunityStage
    stage_changed_at: datetime
    created_at: datetime
    lost_reason: LostReason | None
    competitor_advisor: str | None
    revisit_date: date | None
    mandate_id: int | None
    conflict_warning: Annotated[bool, Field(description="The company or its group is on an active mandate")]
    is_owner: bool


class OpportunityRead(OpportunityListItem):
    members: list[MemberRead]
    links: list[LinkRead]
    credentials: list[CredentialRead]
    fee_draft: Annotated[dict[str, Any] | None, Field(description="Present only with fees.read")] = None


class ConflictWarning(BaseModel):
    conflict_warning: bool


class WinRead(BaseModel):
    id: int
    stage: OpportunityStage
    mandate_id: int


class OriginationSettingsValues(BaseModel):
    dormant_days: Annotated[int, Field(ge=7, le=3650)]


FeeDraft = FeeTermsValues
