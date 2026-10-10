from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

Text = Annotated[str, Field(max_length=1000)]


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class AccessRequestCreate(BaseModel):
    code_name: Annotated[str, Field(min_length=1, max_length=100, examples=["Falcon"])]
    reason: Annotated[Text, Field(examples=["Need sector expertise for the buyer list"])]


class AccessDecision(BaseModel):
    decision: Decision
    reason: Text | None = None
    # Approval only: when access ends. Default 30 days from now.
    expires_at: datetime | None = None


class CommentCreate(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=2000)]
    recommendation: Decision | None = None


class CommentRead(BaseModel):
    author_name: str
    on_behalf_of_name: str | None
    body: str
    recommendation: Decision | None
    label: str
    created_at: datetime


class ConflictingDeal(BaseModel):
    mandate_id: int
    code_name: str
    company_name: str


class MyAccessRequest(BaseModel):
    id: int
    code_name: str
    reason: str
    status: RequestStatus
    created_at: datetime
    decision_reason: str | None
    expires_at: datetime | None


class AccessRequestItem(BaseModel):
    id: int
    code_name: str
    requester_name: str
    reason: str
    status: RequestStatus
    created_at: datetime


class AccessRequestContext(BaseModel):
    """What an approver sees: the request, never the deal itself (AUTHZ-07 c4)."""

    id: int
    code_name: str
    requester_id: int
    requester_name: str
    reason: str
    status: RequestStatus
    created_at: datetime
    decision_reason: str | None
    decided_by_name: str | None
    expires_at: datetime | None
    # Compliance only; empty for the partner and delegates.
    conflicts: list[ConflictingDeal]
    comments: list[CommentRead]
    can_decide: bool
    can_comment: bool


class DelegationCreate(BaseModel):
    delegate_id: int
    starts_on: date
    ends_on: date


class DelegationRead(BaseModel):
    id: int
    delegate_id: int
    delegate_name: str
    starts_on: date
    ends_on: date
    active: bool


class BreakGlassCreate(BaseModel):
    code_name: Annotated[str, Field(min_length=1, max_length=100)]
    reason: Text


class BreakGlassRead(BaseModel):
    mandate_id: int
    code_name: str
    expires_at: datetime


class ReviewMember(BaseModel):
    user_id: int
    name: str
    role: str


class AccessReviewRead(BaseModel):
    id: int
    mandate_id: int
    code_name: str
    quarter: str
    partner_name: str
    due_at: datetime
    completed_at: datetime | None
    escalated_at: datetime | None
    # Only the reviewing partner sees the team.
    members: list[ReviewMember]


class AccessReviewSubmit(BaseModel):
    remove_user_ids: list[int] = Field(default_factory=list)
