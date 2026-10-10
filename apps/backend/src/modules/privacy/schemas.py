from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class LegalHoldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=3, max_length=300, examples=["AML 10-year retention"])]
    until: datetime | None = None


class LegalHoldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    reason: str
    created_at: datetime
    until: datetime | None
    released_at: datetime | None


class ErasureResult(BaseModel):
    contact_id: int
    activities_cleaned: int
    notes_cleaned: int


class RetentionPolicyValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inactive_years: int = Field(ge=1, le=30)


class ReviewDecision(StrEnum):
    KEEP = "keep"
    ANONYMISE = "anonymise"


class ReviewDecide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision


class RetentionReviewRead(BaseModel):
    id: int
    contact_id: int
    contact_name: str
    owner_id: int | None
    asked_at: datetime
    last_interaction_at: datetime
    decision: ReviewDecision | None
    decided_at: datetime | None
