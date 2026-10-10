from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class Opportunity(Base):
    """A potential mandate before it is signed (ORI-01). Seen only by its owner and invited colleagues."""

    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_ev: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    probability: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stage_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sector_id: Mapped[int | None] = mapped_column(
        ForeignKey("picklist_values.id", ondelete="RESTRICT"), index=True, default=None
    )
    lost_reason: Mapped[str | None] = mapped_column(String(32), default=None)
    competitor_advisor: Mapped[str | None] = mapped_column(String(200), default=None)
    revisit_date: Mapped[date | None] = mapped_column(Date, default=None)
    # Set once the revisit task went out, cleared by every new On hold.
    revisit_tasked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # The last reconnect task: a prospect gets one per dormant spell.
    dormant_tasked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Fee terms agreed in the pitch, in the shape of fee.schemas.FeeTermsValues; copied to the mandate on Won.
    fee_draft: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    mandate_id: Mapped[int | None] = mapped_column(ForeignKey("mandates.id", ondelete="SET NULL"), index=True, default=None)


class OpportunityMember(Base):
    __tablename__ = "opportunity_members"
    __table_args__ = (Index("ix_opportunity_members_unique", "opportunity_id", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityLink(Base):
    """A pitch deck or other document link. The CRM stores links, never files."""

    __tablename__ = "opportunity_links"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityCredential(Base):
    """A past deal cited in the pitch: only closed-won deals with a tombstone allowed."""

    __tablename__ = "opportunity_credentials"
    __table_args__ = (Index("ix_opportunity_credentials_unique", "opportunity_id", "mandate_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OriginationSettings(Base):
    """One row (id 1): the dormant-prospect threshold (ORI-04)."""

    __tablename__ = "origination_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=True)
    dormant_days: Mapped[int] = mapped_column(Integer, default=90)
