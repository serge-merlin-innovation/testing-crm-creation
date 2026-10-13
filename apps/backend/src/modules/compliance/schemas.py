from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from ..mandate.schemas import ConflictStatus
from ..mandate.stages import DealStage


class ConflictDecisionKind(StrEnum):
    CLEAR = "clear"
    REJECT = "reject"


class KycStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    FROZEN = "frozen"


Reason = Annotated[str | None, Field(max_length=1000, examples=["Different teams, no overlap"])]


class ConflictDecision(BaseModel):
    decision: ConflictDecisionKind
    reason: Reason = None


class ConflictDecisionRead(BaseModel):
    conflict_status: ConflictStatus
    decision: ConflictDecisionKind
    reason: str
    decided_by: int
    decided_by_name: str
    decided_at: datetime


class ConflictHitRead(BaseModel):
    company_id: int
    company_name: str
    role: str
    matched_company_id: int
    matched_company_name: str
    other_mandate_id: int
    other_code_name: str
    other_role: str
    other_stage: DealStage


class ConflictReviewItem(BaseModel):
    mandate_id: int
    code_name: str
    opened_at: datetime
    hits: int


class CounterpartyCreate(BaseModel):
    company_id: int


class CounterpartyRead(BaseModel):
    company_id: int
    name: str
    added_at: datetime
    conflict_status: ConflictStatus


class KycReview(BaseModel):
    ubo_check: bool = False
    id_check: bool = False
    pep_sanctions_screening: bool = False
    sanctions_hit: bool = False


class KycRead(BaseModel):
    status: KycStatus
    ubo_check: bool
    id_check: bool
    pep_sanctions_screening: bool
    sanctions_hit: bool
    reviewed_at: datetime | None
    approved_at: datetime | None
    reviewer_id: int | None
    reviewer_name: str | None
    frozen: bool
    can_review: bool


class Unfreeze(BaseModel):
    reason: Reason = None
