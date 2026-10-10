from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from ..contact.schemas import ContactLanguage


class OfferRound(StrEnum):
    INDICATIVE = "indicative"
    BINDING = "binding"


class FinancingCertainty(StrEnum):
    COMMITTED = "committed"
    HIGHLY_CONFIDENT = "highly_confident"
    SUBJECT_TO_FINANCING = "subject_to_financing"
    EQUITY_ONLY = "equity_only"


class TemplateKind(StrEnum):
    LETTER = "letter"
    REPORT = "report"


Pct = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, description="EUR millions")]


class OfferCreate(BaseModel):
    buyer_id: int
    round: OfferRound
    ev: Money
    equity_value: Money
    cash_pct: Pct = Decimal("100")
    earn_out_pct: Pct = Decimal("0")
    vendor_loan_pct: Pct = Decimal("0")
    rollover_pct: Pct = Decimal("0")
    conditions: Annotated[str, Field(max_length=2000)] = ""
    financing_certainty: FinancingCertainty
    # Defaults to now: when the offer reached the firm, which decides lateness.
    received_at: datetime | None = None

    @model_validator(mode="after")
    def structure_adds_up(self) -> "OfferCreate":
        total = self.cash_pct + self.earn_out_pct + self.vendor_loan_pct + self.rollover_pct
        if total != Decimal("100"):
            raise ValueError("Cash, earn-out, vendor loan and rollover must add up to 100%")
        return self


class OfferRead(BaseModel):
    id: int
    buyer_id: int
    buyer_name: str
    round: OfferRound
    version: int
    ev: Decimal
    equity_value: Decimal
    cash_pct: Decimal
    earn_out_pct: Decimal
    vendor_loan_pct: Decimal
    rollover_pct: Decimal
    conditions: str
    financing_certainty: FinancingCertainty
    received_at: datetime
    late: bool
    entered_by_name: str
    entered_at: datetime
    ev_ebitda: Decimal | None


class OfferComparison(BaseModel):
    # EUR thousands, from the target's latest year; None when the target has no EBITDA.
    ebitda: Decimal | None
    ebitda_year: int | None
    # Latest version per buyer and round, EV descending.
    bids: list[OfferRead]
    history: list[OfferRead]
    deadlines: "BidDeadlines"


class BidDeadlines(BaseModel):
    indicative_at: datetime | None = None
    binding_at: datetime | None = None


class TemplateWrite(BaseModel):
    kind: TemplateKind
    name: Annotated[str, Field(min_length=1, max_length=100)]
    language: ContactLanguage
    subject: Annotated[str, Field(min_length=1, max_length=300)]
    body: Annotated[str, Field(min_length=1, max_length=20000)]
    references_im: bool = False


class TemplateRead(TemplateWrite):
    id: int
    updated_at: datetime
    updated_by_name: str | None


class LetterRequest(BaseModel):
    template_name: Annotated[str, Field(min_length=1, max_length=100)]
    buyer_ids: Annotated[list[int], Field(min_length=1, max_length=500)]


class ExclusionReason(StrEnum):
    NOT_ACTIVE = "not_active"
    NO_SIGNED_NDA = "no_signed_nda"
    OPTED_OUT = "opted_out"
    DO_NOT_CONTACT = "do_not_contact"
    NO_CONTACT = "no_contact"
    NO_EMAIL = "no_email"
    NO_TEMPLATE_LANGUAGE = "no_template_language"


class LetterSent(BaseModel):
    buyer_id: int
    buyer_name: str
    contact_name: str
    language: ContactLanguage
    subject: str
    body: str
    document_id: int


class LetterExcluded(BaseModel):
    buyer_id: int
    buyer_name: str
    reason: ExclusionReason
    message: str


class LetterResult(BaseModel):
    sent: list[LetterSent]
    excluded: list[LetterExcluded]


class FunnelStep(BaseModel):
    key: str
    count: int
    # Share of the previous step that reached this one; the first step is 100.
    conversion_pct: Decimal | None


class Funnel(BaseModel):
    code_name: str
    steps: list[FunnelStep]


class GeneratedRead(BaseModel):
    id: int
    kind: TemplateKind
    language: ContactLanguage
    subject: str
    body: str
    created_at: datetime
    buyer_id: int | None
    contact_id: int | None


class ReportRequest(BaseModel):
    template_name: Annotated[str, Field(min_length=1, max_length=100)] = "Status report"


OfferComparison.model_rebuild()
