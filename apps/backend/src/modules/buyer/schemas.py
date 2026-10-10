from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class Stake(StrEnum):
    MAJORITY = "majority"
    MINORITY = "minority"
    BOTH = "both"


class BuyerStatus(StrEnum):
    LONG_LIST = "long_list"
    CLIENT_APPROVED = "client_approved"
    CONTACTED = "contacted"
    TEASER_SENT = "teaser_sent"
    NDA_SENT = "nda_sent"
    NDA_SIGNED = "nda_signed"
    IM_SENT = "im_sent"
    INDICATIVE_OFFER = "indicative_offer"
    DATA_ROOM_ACCESS = "data_room_access"
    BINDING_OFFER = "binding_offer"
    PREFERRED_BIDDER = "preferred_bidder"
    DECLINED = "declined"


class Approval(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EXCLUDED = "excluded"


class DeclineReason(StrEnum):
    PRICE = "price"
    FIT = "fit"
    TIMING = "timing"
    NO_RESPONSE = "no_response"


class WarningReason(StrEnum):
    CONFLICT = "conflict"
    CLIENT_EXCLUSION = "client_exclusion"


Millions = Annotated[Decimal | None, Field(ge=0, max_digits=12, decimal_places=2, description="EUR millions")]
Multiple = Annotated[Decimal | None, Field(ge=0, max_digits=8, decimal_places=2, description="EV / EBITDA")]
Rationale = Annotated[str, Field(max_length=1000)]


class InvestorProfileUpdate(BaseModel):
    sector_ids: Annotated[list[int], Field(max_length=50)] = []
    country_ids: Annotated[list[int], Field(max_length=100)] = []
    ticket_min: Millions = None
    ticket_max: Millions = None
    ev_ebitda_min: Multiple = None
    ev_ebitda_max: Multiple = None
    stake: Stake | None = None

    @model_validator(mode="after")
    def _ranges(self) -> "InvestorProfileUpdate":
        for low, high in (("ticket_min", "ticket_max"), ("ev_ebitda_min", "ev_ebitda_max")):
            lo, hi = getattr(self, low), getattr(self, high)
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f"{low} must not exceed {high}")
        return self


class PortfolioEntity(BaseModel):
    id: int
    name: str


class PastDecline(BaseModel):
    mandate_id: int
    code_name: str
    reason: DeclineReason
    declined_at: datetime


class InvestorProfileRead(BaseModel):
    company_id: int
    has_profile: bool
    sector_ids: list[int]
    country_ids: list[int]
    ticket_min: Decimal | None
    ticket_max: Decimal | None
    ev_ebitda_min: Decimal | None
    ev_ebitda_max: Decimal | None
    stake: Stake | None
    updated_at: datetime | None
    outdated: bool
    portfolio: list[PortfolioEntity]
    declines: list[PastDecline]
    standstill_end: date | None
    non_solicit_end: date | None


class CompanyRef(BaseModel):
    company_id: int


class ExclusionRead(BaseModel):
    company_id: int
    name: str
    added_at: datetime


class Suggestion(BaseModel):
    company_id: int
    name: str
    type: str
    score: int
    matched: list[str]


class BuyerItem(BaseModel):
    company_id: int
    owner_id: int
    rationale: Rationale
    contact_id: int | None = None


class BuyersAdd(BaseModel):
    items: Annotated[list[BuyerItem], Field(min_length=1, max_length=200)]
    confirm: bool = Field(default=False, description="Add even buyers with a conflict or on the client's exclusion list")


class AddWarning(BaseModel):
    company_id: int
    name: str
    reason: WarningReason


class BuyersAdded(BaseModel):
    added: list[int]
    skipped: list[int]
    warnings: list[AddWarning]


class BuyerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: int | None = None
    rationale: Rationale | None = None
    contact_id: int | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None
    approval: Approval | None = None


class StatusChange(BaseModel):
    buyer_ids: Annotated[list[int], Field(min_length=1, max_length=500)]
    status: BuyerStatus
    decline_reason: DeclineReason | None = None


class NdaUpdate(BaseModel):
    sent_date: date | None = None
    markup_received_date: date | None = None
    agreed_date: date | None = None
    signed_date: date | None = None
    document_url: AnyHttpUrl | None = None
    standstill_end: date | None = None
    non_solicit_end: date | None = None

    @field_validator("document_url")
    @classmethod
    def _https(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("Use an https link")
        return value


class NdaRead(BaseModel):
    sent_date: date | None
    markup_received_date: date | None
    agreed_date: date | None
    signed_date: date | None
    document_url: str | None
    standstill_end: date | None
    non_solicit_end: date | None


class BuyerRead(BaseModel):
    id: int
    company_id: int
    name: str
    type: str
    owner_id: int
    owner_name: str
    rationale: str
    contact_id: int | None
    contact_name: str | None
    approval: Approval
    status: BuyerStatus
    status_changed_at: datetime
    status_changed_by_name: str
    decline_reason: DeclineReason | None
    notes: str | None
    nda: NdaRead | None


class BuyerGrid(BaseModel):
    buyers: list[BuyerRead]
    funnel: dict[str, int]
    can_approve: bool


class ContactBuyerRole(BaseModel):
    mandate_id: int
    code_name: str
    company_id: int
    status: BuyerStatus
