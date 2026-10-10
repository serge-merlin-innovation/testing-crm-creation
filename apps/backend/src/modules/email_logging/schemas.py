from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from ..activity.schemas import RecordRef

Address = Annotated[str, Field(max_length=500)]


class InboundAttachment(BaseModel):
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    # Accepted so a provider payload validates, then dropped: only the name is ever stored.
    content: str | None = None
    content_type: str | None = None


class InboundEmail(BaseModel):
    """The inbound-parse port: what a mail provider's webhook adapter hands the CRM, normalized."""

    sender: Address
    to: Annotated[list[Address], Field(max_length=200)] = []
    cc: Annotated[list[Address], Field(max_length=200)] = []
    bcc: Annotated[list[Address], Field(max_length=200)] = []
    subject: Annotated[str, Field(max_length=2000)] = ""
    text: Annotated[str, Field(max_length=1_000_000)] = ""
    message_id: Annotated[str, Field(max_length=255)] | None = None
    date: datetime | None = None
    attachments: Annotated[list[InboundAttachment], Field(max_length=100)] = []


class InboundStatus(StrEnum):
    LOGGED = "logged"
    UNMATCHED = "unmatched"


class InboundResult(BaseModel):
    status: InboundStatus
    activity_id: int | None = None
    unmatched_id: int | None = None


class LoggingAddressRead(BaseModel):
    address: str


class UnmatchedRead(BaseModel):
    id: int
    sender: str
    subject: str
    body: str
    correspondents: list[str]
    attachment_names: list[str]
    occurred_at: datetime
    received_at: datetime
    mandate_id: int | None


class UnmatchedLink(BaseModel):
    links: Annotated[list[RecordRef], Field(min_length=1, max_length=20)]


class InteractionRead(BaseModel):
    """CON-02 c2: how well one colleague knows a contact, from logged emails and meetings."""

    user_id: int
    name: str
    count: int
    last_interaction_at: datetime
