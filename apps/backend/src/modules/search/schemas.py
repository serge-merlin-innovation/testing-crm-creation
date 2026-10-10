from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from ..company.schemas import CompanyType
from ..contact.schemas import HolderRead

MIN_QUERY_LENGTH = 3


class SearchCriteria(BaseModel):
    """What a saved filter stores. Company criteria narrow companies (and contacts through their
    current company); EV bounds narrow deals, in EUR thousands."""

    q: Annotated[str | None, Field(max_length=200)] = None
    company_types: list[CompanyType] = Field(default_factory=list)
    country_ids: list[int] = Field(default_factory=list)
    sector_ids: list[int] = Field(default_factory=list)
    ev_min: Decimal | None = None
    ev_max: Decimal | None = None

    def has_criteria(self) -> bool:
        return bool(
            self.company_types or self.country_ids or self.sector_ids or self.ev_min is not None or self.ev_max is not None
        )


class CompanyHit(BaseModel):
    id: int
    name: str
    type: CompanyType
    country_id: int


class ContactHit(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    company_id: int | None
    relationship_holders: list[HolderRead]


class DealHit(BaseModel):
    id: int
    code_name: str
    stage: str


class SearchResults(BaseModel):
    query: str
    companies: list[CompanyHit]
    contacts: list[ContactHit]
    deals: list[DealHit]


class SavedFilterCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100, examples=["PE funds Benelux, EV 10-50m"])]
    criteria: SearchCriteria
    shared: bool = False


class SavedFilterRead(BaseModel):
    id: int
    owner_id: int
    owner_name: str
    name: str
    criteria: SearchCriteria
    shared: bool
    created_at: datetime


class ShareUpdate(BaseModel):
    shared: bool
