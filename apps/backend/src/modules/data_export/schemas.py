from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContactFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: Annotated[str | None, Field(max_length=200)] = None


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter: ContactFilter = ContactFilter()
    reason: Annotated[str, Field(min_length=3, max_length=500, examples=["Mailing for the Benelux PE event"])]


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool


class ApprovalRead(BaseModel):
    id: int
    requested_by: int
    requested_by_name: str | None
    kind: str
    filter: ContactFilter
    row_count: int
    reason: str
    requested_at: datetime
    status: ApprovalStatus
    decided_by: int | None
    decided_at: datetime | None
    used_at: datetime | None


class ExportPreview(BaseModel):
    row_count: int
    needs_approval: bool
    limit: int
