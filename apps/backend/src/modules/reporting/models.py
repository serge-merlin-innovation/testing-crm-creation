from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class DealForecast(Base):
    """The team's view of when a deal closes and how likely it is (REP-02, REP-03)."""

    __tablename__ = "deal_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True, unique=True)
    updated_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # None falls back to the stage default (STAGE_PROBABILITY).
    probability: Mapped[int | None] = mapped_column(Integer, default=None)
    expected_closing_date: Mapped[date | None] = mapped_column(Date, default=None)
