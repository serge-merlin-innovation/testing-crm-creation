from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..mandate.stages import DealStage
from ..task.schemas import TaskRead


class ForecastValues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probability: Annotated[int | None, Field(ge=0, le=100, description="Percent; null = the stage default")] = None
    expected_closing_date: date | None = None


class ForecastRead(BaseModel):
    mandate_id: int
    probability: int
    probability_is_default: bool
    expected_closing_date: date | None


class HomeDeal(BaseModel):
    id: int
    code_name: str
    stage: DealStage


class HomeStage(BaseModel):
    stage: DealStage
    deals: list[HomeDeal]


class KeyDate(BaseModel):
    mandate_id: int
    code_name: str
    name: str
    planned_date: date


class HomeRead(BaseModel):
    deals_by_stage: list[HomeStage]
    tasks_due_this_week: list[TaskRead]
    key_dates: list[KeyDate]
    week_start: date
    week_end: date
    is_new: bool


class StageTypeCount(BaseModel):
    stage: DealStage
    type: str
    count: int


class QuarterFees(BaseModel):
    quarter: str = Field(description="YYYY-Qn, or 'unscheduled' for deals without an expected closing date")
    deals: int
    expected_fees: Decimal
    weighted_fees: Decimal


class DashboardRead(BaseModel):
    total_mandates: int
    by_stage_and_type: list[StageTypeCount]
    # Absent for a caller without fee visibility (AUTHZ-06).
    weighted_fees_by_quarter: list[QuarterFees] | None = None
    # Firm-wide weighted fees of deals the caller is not staffed on; null below 3 such deals.
    other_teams_weighted_fees: Decimal | None = None


class ForecastMonth(BaseModel):
    month: str = Field(description="YYYY-MM")
    retainers: Decimal
    success_fees: Decimal
    forecast_total: Decimal
    actual_invoiced: Decimal
    actual_paid: Decimal


class FeeForecastRead(BaseModel):
    months: list[ForecastMonth]
    deals: int


class ReasonCount(BaseModel):
    reason: str
    count: int


class SectorMultiple(BaseModel):
    sector_id: int
    sector: str
    deals: int
    average_ev_ebitda: Decimal


class WinLossRead(BaseModel):
    period_start: date
    period_end: date
    pitches: int
    won: int
    lost: int
    win_rate: Decimal | None = Field(description="Percent of decided pitches won; null when none were decided")
    top_lost_reasons: list[ReasonCount]
    closed_deals: int
    average_duration_days: Decimal | None
    ev_ebitda_by_sector: list[SectorMultiple]
