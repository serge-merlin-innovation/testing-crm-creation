from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..contact.schemas import ContactLanguage
from .enterprise_number import normalize_enterprise_number


class CompanyType(StrEnum):
    TARGET = "target"
    STRATEGIC_BUYER = "strategic_buyer"
    FINANCIAL_INVESTOR = "financial_investor"
    LENDER = "lender"
    ADVISOR = "advisor"
    OTHER = "other"


class Metric(StrEnum):
    REVENUE = "revenue"
    EBITDA = "ebitda"
    NET_DEBT = "net_debt"
    FTE = "fte"


class FigureSource(StrEnum):
    NBB = "nbb"
    MANUAL = "manual"


def _checked_enterprise_number(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    digits = normalize_enterprise_number(value)
    if digits is None:
        raise ValueError("Invalid enterprise number: the checksum does not match")
    return digits


EnterpriseNumber = Annotated[str | None, Field(default=None, examples=["BE0403.170.701"])]


class EnterpriseNumberLookup(BaseModel):
    enterprise_number: str

    @field_validator("enterprise_number")
    @classmethod
    def enterprise_number_checksum(cls, value: str) -> str | None:
        return _checked_enterprise_number(value)


class RegisterPrefill(BaseModel):
    enterprise_number: str
    available: bool
    name: str | None = None
    address: str | None = None
    nace_code: str | None = None
    legal_form: str | None = None


class CompanyCreate(BaseModel):
    name: Annotated[str | None, Field(max_length=200)] = None
    type: CompanyType
    country_id: int
    sector_id: int | None = None
    enterprise_number: EnterpriseNumber = None
    vat_or_registry_number: Annotated[str | None, Field(max_length=64)] = None
    legal_form: Annotated[str | None, Field(max_length=100)] = None
    nace_code: Annotated[str | None, Field(max_length=16)] = None
    address: Annotated[str | None, Field(max_length=400)] = None
    parent_id: int | None = None
    language: ContactLanguage = ContactLanguage.EN
    # Set after the user saw the similar-name duplicates and chose to create anyway.
    ignore_similar: bool = False

    @field_validator("enterprise_number")
    @classmethod
    def enterprise_number_checksum(cls, value: str | None) -> str | None:
        return _checked_enterprise_number(value)


class CompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    type: CompanyType | None = None
    sector_id: int | None = None
    vat_or_registry_number: Annotated[str | None, Field(max_length=64)] = None
    legal_form: Annotated[str | None, Field(max_length=100)] = None
    nace_code: Annotated[str | None, Field(max_length=16)] = None
    address: Annotated[str | None, Field(max_length=400)] = None
    parent_id: int | None = None
    language: ContactLanguage | None = None


class DuplicateCompany(BaseModel):
    id: int
    name: str
    enterprise_number: str | None
    reason: str
    url: str


class CompanyRead(BaseModel):
    id: int
    name: str
    type: CompanyType
    country_id: int
    sector_id: int | None
    enterprise_number: str | None
    vat_or_registry_number: str | None
    legal_form: str | None
    nace_code: str | None
    address: str | None
    register_source: str | None
    parent_id: int | None
    language: ContactLanguage = ContactLanguage.EN


class GroupNode(BaseModel):
    id: int
    name: str
    children: list["GroupNode"] = Field(default_factory=list)


class CompanyDetail(CompanyRead):
    group: GroupNode


class FinancialYearEntry(BaseModel):
    revenue: Decimal | None = None
    ebitda: Decimal | None = None
    net_debt: Decimal | None = None
    fte: Decimal | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "EUR"
    eur_rate: Annotated[Decimal | None, Field(gt=0)] = None

    @model_validator(mode="after")
    def foreign_currency_needs_rate(self) -> "FinancialYearEntry":
        if self.currency != "EUR" and self.eur_rate is None:
            raise ValueError("eur_rate is required for figures not in EUR")
        return self


class FigureRead(BaseModel):
    value: Decimal
    source: FigureSource
    recorded_at: datetime
    recorded_by: int | None
    source_date: date | None
    original_currency: str
    original_value: Decimal | None
    eur_rate: Decimal | None


class MetricRead(BaseModel):
    value: Decimal
    imported: FigureRead | None
    override: FigureRead | None


class FinancialYearRead(BaseModel):
    year: int
    metrics: dict[Metric, MetricRead]


GroupNode.model_rebuild()
