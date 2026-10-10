from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from ..common.validators import optional_https_url

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, description="EUR")]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=6, decimal_places=3)]


class SuccessFeeKind(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"
    LEHMAN = "lehman"


class LehmanTier(BaseModel):
    up_to: Annotated[Decimal | None, Field(gt=0, description="Upper EV bound in EUR thousands; null = no bound")] = None
    percent: Percent


class FeeTermsValues(BaseModel):
    retainer_monthly: Money = Decimal("0")
    success_fee_kind: SuccessFeeKind = SuccessFeeKind.PERCENT
    success_fee_percent: Percent | None = None
    success_fee_fixed: Money | None = None
    minimum_fee: Money = Decimal("0")
    lehman_tiers: list[LehmanTier] = Field(default_factory=list)
    retainers_creditable: bool = False
    change_reason: Annotated[str | None, Field(max_length=1000, description="Required for a change after engagement")] = None
    amended_letter_url: Annotated[
        str | None,
        Field(max_length=2000, description="Amended engagement letter, required with the reason"),
        AfterValidator(optional_https_url),
    ] = None

    @model_validator(mode="after")
    def kind_has_its_value(self) -> Self:
        if self.success_fee_kind == SuccessFeeKind.PERCENT and self.success_fee_percent is None:
            raise ValueError("Give the success fee percentage")
        if self.success_fee_kind == SuccessFeeKind.FIXED and self.success_fee_fixed is None:
            raise ValueError("Give the fixed success fee")
        if self.success_fee_kind == SuccessFeeKind.LEHMAN:
            tiers = self.lehman_tiers
            if not tiers or tiers[-1].up_to is not None:
                raise ValueError("Lehman tiers must end with an open band (no upper bound)")
            bounds = [tier.up_to for tier in tiers[:-1]]
            if any(bound is None for bound in bounds) or bounds != sorted(bounds) or len(set(bounds)) != len(bounds):  # type: ignore[type-var]
                raise ValueError("Lehman tier bounds must ascend")
        return self


class FeeTermsRead(BaseModel):
    mandate_id: int
    code_name: str
    retainer_monthly: Decimal
    success_fee_kind: SuccessFeeKind
    success_fee_percent: Decimal | None
    success_fee_fixed: Decimal | None
    minimum_fee: Decimal
    lehman_tiers: list[LehmanTier]
    retainers_creditable: bool
    retainers_paid: Decimal
    expected_fee: Decimal
    final_fee: Decimal | None
    engaged: bool
    can_edit: bool


class InvoiceType(StrEnum):
    RETAINER = "retainer"
    SUCCESS_FEE = "success_fee"


class InvoiceCreate(BaseModel):
    type: InvoiceType
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2, description="EUR")]
    sent_date: date
    paid_date: date | None = None


class InvoiceUpdate(BaseModel):
    paid_date: date | None = None


class InvoiceRead(BaseModel):
    id: int
    mandate_id: int
    type: InvoiceType
    amount: Decimal
    sent_date: date
    paid_date: date | None
