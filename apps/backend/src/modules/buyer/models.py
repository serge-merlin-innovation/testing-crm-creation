from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class InvestorProfile(Base):
    """A buyer company's investment criteria (CO-04) and the restrictions its signed NDAs put on it (BUY-04 c3)."""

    __tablename__ = "investor_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), unique=True, index=True)
    # EUR millions.
    ticket_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    ticket_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    ev_ebitda_min: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), default=None)
    ev_ebitda_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), default=None)
    stake: Mapped[str | None] = mapped_column(String(16), default=None)
    # When the criteria were last saved: the 12-month staleness flag reads it, NDA restrictions do not touch it.
    criteria_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    criteria_updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    standstill_end: Mapped[date | None] = mapped_column(Date, default=None)
    non_solicit_end: Mapped[date | None] = mapped_column(Date, default=None)


class InvestorCriterion(Base):
    """One sector or geography a buyer invests in."""

    __tablename__ = "investor_criteria"
    __table_args__ = (Index("ix_investor_criteria_unique", "company_id", "kind", "value_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value_id: Mapped[int] = mapped_column(ForeignKey("picklist_values.id", ondelete="RESTRICT"), index=True)


class ClientExclusion(Base):
    """A company the client does not want approached in any of its processes (BUY-01 c3)."""

    __tablename__ = "client_exclusions"
    __table_args__ = (Index("ix_client_exclusions_unique", "client_id", "company_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DealBuyer(Base):
    """A buyer on a deal's list: its approval by the client and where it stands in the process."""

    __tablename__ = "deal_buyers"
    __table_args__ = (Index("ix_deal_buyers_unique", "mandate_id", "company_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_changed_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    # Any change to the buyer: the 14-day idle reminder counts from here.
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True, default=None)
    approval: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Internal only: never exported to the client.
    notes: Mapped[str | None] = mapped_column(String(2000), default=None)
    decline_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    idle_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class BuyerNda(Base):
    __tablename__ = "buyer_ndas"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("deal_buyers.id", ondelete="CASCADE"), unique=True, index=True)
    sent_date: Mapped[date | None] = mapped_column(Date, default=None)
    markup_received_date: Mapped[date | None] = mapped_column(Date, default=None)
    agreed_date: Mapped[date | None] = mapped_column(Date, default=None)
    signed_date: Mapped[date | None] = mapped_column(Date, default=None)
    document_url: Mapped[str | None] = mapped_column(String(2000), default=None)
    standstill_end: Mapped[date | None] = mapped_column(Date, default=None)
    non_solicit_end: Mapped[date | None] = mapped_column(Date, default=None)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
