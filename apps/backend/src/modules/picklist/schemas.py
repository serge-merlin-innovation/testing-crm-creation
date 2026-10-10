from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Label = Annotated[str, Field(min_length=1, max_length=200)]


class PicklistKind(StrEnum):
    SECTOR = "sector"
    DEAL_STAGE = "deal_stage"
    DEAL_TYPE = "deal_type"
    COUNTRY = "country"


class Language(StrEnum):
    EN = "en"
    FR = "fr"
    NL = "nl"


class PicklistValueCreate(BaseModel):
    kind: PicklistKind
    code: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]
    label_en: Label
    label_fr: Label | None = None
    label_nl: Label | None = None


class PicklistValueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_en: Label | None = None
    label_fr: Label | None = None
    label_nl: Label | None = None
    is_active: bool | None = None


class PicklistValueRead(BaseModel):
    id: int
    kind: PicklistKind
    code: str
    label_en: str
    label_fr: str | None
    label_nl: str | None
    is_active: bool
    label: str
    translated: bool
