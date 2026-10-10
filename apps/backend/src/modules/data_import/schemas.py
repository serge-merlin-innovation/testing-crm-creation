from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ImportEntity(StrEnum):
    CONTACT = "contact"
    COMPANY = "company"


class RowStatus(StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    ERROR = "error"


class ImportStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    COMPLETED = "completed"


# Fields an import can fill, per entity. `company` on a contact names an existing company; `country`
# on a company is its ISO code (BE, NL, ...).
TARGET_FIELDS: dict[ImportEntity, tuple[str, ...]] = {
    ImportEntity.CONTACT: (
        "first_name",
        "last_name",
        "email",
        "phone",
        "language",
        "salutation",
        "company",
        "function",
        "source",
    ),
    ImportEntity.COMPANY: (
        "name",
        "type",
        "country",
        "enterprise_number",
        "vat_or_registry_number",
        "legal_form",
        "nace_code",
        "address",
    ),
}
REQUIRED_FIELDS: dict[ImportEntity, tuple[str, ...]] = {
    ImportEntity.CONTACT: ("first_name", "last_name"),
    ImportEntity.COMPANY: ("name", "type", "country"),
}


class UploadRead(BaseModel):
    id: int
    entity: ImportEntity
    filename: str
    status: ImportStatus
    headers: list[str]
    row_count: int
    fields: list[str]
    required_fields: list[str]
    suggested_mapping: dict[str, str]
    uploaded_at: datetime


class MappingRequest(BaseModel):
    # Target field -> column header in the file.
    mapping: dict[str, str] = Field(examples=[{"first_name": "First name", "last_name": "Surname", "email": "E-mail"}])


class RowResult(BaseModel):
    row: int
    status: RowStatus
    values: dict[str, Any]
    errors: list[str] = Field(default_factory=list)
    duplicate_of: int | None = None


class PreviewRead(BaseModel):
    id: int
    status: ImportStatus
    counts: dict[RowStatus, int]
    rows: list[RowResult]


class ImportRead(BaseModel):
    id: int
    entity: ImportEntity
    filename: str
    status: ImportStatus
    row_count: int
    background: bool
    counts: dict[RowStatus, int] | None
    created: int
    error_file_url: str | None
    completed_at: datetime | None
