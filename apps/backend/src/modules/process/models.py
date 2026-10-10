from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class BidDeadline(Base):
    """When indicative and binding bids are due on a deal (BUY-05 c5)."""

    __tablename__ = "bid_deadlines"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), unique=True, index=True)
    indicative_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    binding_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Offer(Base):
    """One version of a buyer's indicative or binding offer. A revision adds a row; earlier ones stay."""

    __tablename__ = "offers"
    __table_args__ = (Index("ix_offers_version", "buyer_id", "round", "version", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("deal_buyers.id", ondelete="CASCADE"), index=True)
    round: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # EUR millions.
    ev: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    equity_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cash_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    earn_out_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    vendor_loan_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rollover_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    conditions: Mapped[str] = mapped_column(String(2000), nullable=False)
    financing_certainty: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    late: Mapped[bool] = mapped_column(Boolean, nullable=False)
    entered_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentTemplate(Base):
    """A process letter or client report wording in one language (ADM-07). `name` groups the languages."""

    __tablename__ = "document_templates"
    __table_args__ = (Index("ix_document_templates_unique", "kind", "name", "language", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    references_im: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)


class GeneratedDocument(Base):
    """A letter or report as it was produced: the rendered text is frozen, so later template edits never change it."""

    __tablename__ = "generated_documents"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_templates.id", ondelete="SET NULL"), index=True, default=None
    )
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("deal_buyers.id", ondelete="SET NULL"), index=True, default=None)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True, default=None)
