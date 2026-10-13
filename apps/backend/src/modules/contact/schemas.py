from datetime import date
from enum import StrEnum
from typing import Annotated

import phonenumbers
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactLanguage(StrEnum):
    EN = "en"
    FR = "fr"
    NL = "nl"


class LegalBasis(StrEnum):
    LEGITIMATE_INTEREST = "legitimate_interest"
    CONSENT = "consent"


DEFAULT_PHONE_REGION = "BE"


def to_e164(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    try:
        number = phonenumbers.parse(raw, DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException as error:
        raise ValueError("Invalid phone number") from error
    if not phonenumbers.is_valid_number(number):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


Name = Annotated[str, Field(min_length=1, max_length=100)]


class ContactCreate(BaseModel):
    first_name: Name
    last_name: Name
    email: EmailStr | None = None
    phone: Annotated[str | None, Field(examples=["+32 2 123 45 67"])] = None
    language: ContactLanguage = ContactLanguage.EN
    salutation: Annotated[str | None, Field(max_length=32)] = None
    do_not_contact: bool = False
    marketing_opt_out: bool = False
    legal_basis: LegalBasis = LegalBasis.LEGITIMATE_INTEREST
    source: Annotated[str, Field(min_length=1, max_length=200, examples=["Met at M&A forum 2026"])]
    company_id: int | None = None
    function: Annotated[str | None, Field(max_length=200)] = None

    _phone = field_validator("phone")(to_e164)


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: Name | None = None
    last_name: Name | None = None
    email: EmailStr | None = None
    phone: str | None = None
    language: ContactLanguage | None = None
    salutation: Annotated[str | None, Field(max_length=32)] = None
    do_not_contact: bool | None = None
    marketing_opt_out: bool | None = None
    legal_basis: LegalBasis | None = None
    source: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    # Changing the company closes the current role (kept as history) and opens a new one.
    company_id: int | None = None
    function: Annotated[str | None, Field(max_length=200)] = None

    _phone = field_validator("phone")(to_e164)


class EmploymentRead(BaseModel):
    company_id: int
    company_name: str = ""
    function: str | None
    start_date: date | None
    end_date: date | None


class ContactRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    language: ContactLanguage
    salutation: str | None
    do_not_contact: bool
    marketing_opt_out: bool
    legal_basis: LegalBasis
    source: str
    current_role: EmploymentRead | None
    history: list[EmploymentRead]
    warnings: list[str] = Field(default_factory=list)
    duplicate_contact_ids: list[int] = Field(default_factory=list)
    relationship_holders: list["HolderRead"] = Field(default_factory=list)


class HolderRead(BaseModel):
    user_id: int
    name: str
    strength: Annotated[int, Field(ge=1, le=3)]


class HolderSet(BaseModel):
    strength: Annotated[int, Field(ge=1, le=3, description="1 acquainted, 2 good, 3 close")]
