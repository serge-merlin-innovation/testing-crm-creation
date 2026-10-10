from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class MergeableType(StrEnum):
    CONTACT = "contact"
    COMPANY = "company"


class Pick(StrEnum):
    SURVIVOR = "survivor"
    DUPLICATE = "duplicate"


class MergeRequest(BaseModel):
    record_type: MergeableType
    survivor_id: int
    duplicate_id: int
    # Field name -> which record's value the survivor keeps. Unlisted fields keep the survivor's.
    fields: dict[str, Pick] = Field(default_factory=dict, examples=[{"email": "duplicate"}])

    @model_validator(mode="after")
    def two_records(self) -> "MergeRequest":
        if self.survivor_id == self.duplicate_id:
            raise ValueError("Pick two different records")
        return self


class MergeRead(BaseModel):
    id: int
    record_type: MergeableType
    survivor_id: int
    duplicate_id: int
    merged_by: int
    merged_at: datetime
    moved: dict[str, int]
    undone_at: datetime | None
