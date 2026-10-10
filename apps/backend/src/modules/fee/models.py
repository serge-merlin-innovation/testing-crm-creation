from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class FeeTerms(Base):
    """The engagement's commercial terms (DEAL-05). Read only with fees.read (AUTHZ-06)."""

    __tablename__ = "fee_terms"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True, unique=True)
    retainer_monthly: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    success_fee_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    minimum_fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    retainers_creditable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    success_fee_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), default=None)
    success_fee_fixed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    # [{"up_to": "10000" | null, "percent": "3"}]: EV bands in EUR thousands, last band open.
    lehman_tiers: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default_factory=list)
    # Set when the deal closes as won, from the final EV.
    final_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)


class Invoice(Base):
    """An invoice back-office sent on a mandate (REP-07). Same visibility as fee fields."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sent_date: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_date: Mapped[date | None] = mapped_column(Date, default=None)


class InvoiceTask(Base):
    """The back-office task raised at closing; the success-fee invoice completes it."""

    __tablename__ = "invoice_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
