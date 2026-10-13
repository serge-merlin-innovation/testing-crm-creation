from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Lowercased, punctuation and legal-form suffixes stripped: what similar-name duplicates compare.
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("picklist_values.id", ondelete="RESTRICT"), index=True)
    sector_id: Mapped[int | None] = mapped_column(
        ForeignKey("picklist_values.id", ondelete="RESTRICT"), index=True, default=None
    )
    # Belgian KBO/BCE number as its 10 digits, no punctuation.
    enterprise_number: Mapped[str | None] = mapped_column(String(10), unique=True, default=None)
    vat_or_registry_number: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    legal_form: Mapped[str | None] = mapped_column(String(100), default=None)
    nace_code: Mapped[str | None] = mapped_column(String(16), default=None)
    address: Mapped[str | None] = mapped_column(String(400), default=None)
    register_source: Mapped[str | None] = mapped_column(String(16), default=None)
    # The client's language: status reports to the client use it (REP-05 c2).
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="en", server_default="en")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True, default=None)


class FinancialFigure(Base):
    """One metric of one year from one source. An NBB import and a manual override live side by side."""

    __tablename__ = "company_financials"
    __table_args__ = (Index("ix_company_financials_unique", "company_id", "year", "metric", "source", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # EUR thousands (FTE: headcount).
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(Integer, default=None)
    source_date: Mapped[date | None] = mapped_column(Date, default=None)
    original_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    original_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), default=None)
    eur_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), default=None)
