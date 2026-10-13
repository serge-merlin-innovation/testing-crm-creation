from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


class ActivityType(StrEnum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"


class RecordType(StrEnum):
    CONTACT = "contact"
    COMPANY = "company"
    MANDATE = "mandate"


class NoteVisibility(StrEnum):
    SHARED = "shared"
    PRIVATE = "private"
    DEAL_CONFIDENTIAL = "deal_confidential"


class RecordRef(BaseModel):
    record_type: RecordType
    record_id: int


Participants = Annotated[list[Annotated[str, Field(min_length=1, max_length=200)]], Field(max_length=50)]
NoteText = Annotated[str, Field(min_length=1, max_length=20000)]


class ActivityCreate(BaseModel):
    type: ActivityType
    occurred_at: datetime
    participants: Participants = []
    note: NoteText
    links: Annotated[list[RecordRef], Field(min_length=1, max_length=20)]


class ActivityUpdate(BaseModel):
    type: ActivityType | None = None
    occurred_at: datetime | None = None
    participants: Participants | None = None
    note: NoteText | None = None


class ActivityRead(BaseModel):
    id: int
    type: ActivityType
    occurred_at: datetime
    participants: list[str]
    note: str
    author_id: int
    author_name: str | None = None
    created_at: datetime
    links: list[RecordRef]
    # Set only when the activity was changed more than 7 days after it was logged.
    edited_at: datetime | None
    deleted_at: datetime | None = None


class NoteCreate(BaseModel):
    record_type: RecordType
    record_id: int
    body: NoteText
    visibility: NoteVisibility = NoteVisibility.SHARED
    mandate_id: int | None = None

    @model_validator(mode="after")
    def deal_confidential_names_its_deal(self) -> "NoteCreate":
        if self.visibility == NoteVisibility.DEAL_CONFIDENTIAL and self.mandate_id is None:
            if self.record_type != RecordType.MANDATE:
                raise ValueError("A deal-confidential note names its deal")
            self.mandate_id = self.record_id
        return self


class NoteRead(BaseModel):
    id: int
    record_type: RecordType
    record_id: int
    body: str
    visibility: NoteVisibility
    author_id: int
    author_name: str | None = None
    created_at: datetime
    mandate_id: int | None


class DealRef(BaseModel):
    id: int
    code_name: str


class TimelineRead(BaseModel):
    activities: list[ActivityRead]
    notes: list[NoteRead]
    # Deals this company is client or target of, only those the reader is staffed on.
    deals: list[DealRef]
