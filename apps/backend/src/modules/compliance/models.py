from datetime import datetime

from sqlalchemy import DDL, Boolean, DateTime, ForeignKey, Index, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class DealCounterparty(Base):
    """A known counterparty of a deal (buyer, co-investor, lender...), part of the conflict check."""

    __tablename__ = "deal_counterparties"
    __table_args__ = (Index("ix_deal_counterparties_unique", "mandate_id", "company_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConflictReview(Base):
    """One run of the conflict check that found hits, and compliance's decision on it."""

    __tablename__ = "conflict_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(16), default=None)
    reason: Mapped[str | None] = mapped_column(String(1000), default=None)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True, default=None
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set when the 5-working-day reminder went out, so it goes once.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ConflictHit(Base):
    __tablename__ = "conflict_hits"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    review_id: Mapped[int] = mapped_column(ForeignKey("conflict_reviews.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    matched_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    other_mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    other_role: Mapped[str] = mapped_column(String(16), nullable=False)


class KycRecord(Base):
    """The KYC of a deal's client (ORI-05): one row per deal, overwritten by each review."""

    __tablename__ = "kyc_records"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    ubo_check: Mapped[bool] = mapped_column(Boolean, nullable=False)
    id_check: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pep_sanctions_screening: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sanctions_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reviewer_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, default=None)
    # The approval a refresh task was already created for, so the daily job creates one per approval.
    refresh_task_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


# Fuzzy name matching needs these. Migrations create them too; this covers `create_all` in tests.
for extension in ("pg_trgm", "unaccent"):
    event.listen(
        DealCounterparty.__table__,
        "before_create",
        DDL(f"CREATE EXTENSION IF NOT EXISTS {extension}").execute_if(dialect="postgresql"),
    )
