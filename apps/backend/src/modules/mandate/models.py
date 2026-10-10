from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class Mandate(Base):
    __tablename__ = "mandates"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    code_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Lowercased code name: uniqueness is case-insensitive.
    code_name_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    sector_id: Mapped[int] = mapped_column(ForeignKey("picklist_values.id", ondelete="RESTRICT"), index=True)
    lead_partner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    estimated_ev: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True, default=None)
    # Optimistic concurrency (DEAL-03): every write must name the version it read.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stage_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Closing (DEAL-06). `closed_at` set means the deal is read-only until a partner reopens it.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, default=None)
    stage_before_close: Mapped[str | None] = mapped_column(String(32), default=None)
    final_ev: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), default=None)
    buyer: Mapped[str | None] = mapped_column(String(200), default=None)
    ev_ebitda: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), default=None)
    closing_date: Mapped[date | None] = mapped_column(Date, default=None)
    tombstone_allowed: Mapped[bool | None] = mapped_column(Boolean, default=None)
    abort_reason: Mapped[str | None] = mapped_column(String(1000), default=None)
    # The conflict check (AUTHZ-05) sets these; `review` and `rejected` hide the deal from all but its
    # creator and compliance (DEAL-01 c4).
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    conflict_status: Mapped[str] = mapped_column(String(16), nullable=False, default="clear", server_default="clear")
    # Set by a sanctions hit (ORI-05 c4): every write is refused until compliance unfreezes.
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class DealTeamMember(Base):
    __tablename__ = "deal_team_members"
    __table_args__ = (Index("ix_deal_team_members_unique", "mandate_id", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class WallCrossing(Base):
    """The wall-crossing register: every time someone is brought over or taken off the wall."""

    __tablename__ = "wall_crossings"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class DealLink(Base):
    """A labelled https link to a file folder or data room. The CRM stores links, never files."""

    __tablename__ = "deal_links"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StageCriterion(Base):
    """An exit criterion of a stage (DEAL-08): every forward move out of `stage` must satisfy it."""

    __tablename__ = "stage_criteria"
    __table_args__ = (Index("ix_stage_criteria_unique", "stage", "kind", "value_key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Lowercased value, so "VDR" and "vdr" are one criterion; empty for the KYC gate.
    value_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[str | None] = mapped_column(String(100), default=None)
    # The built-in engagement letter / KYC gate is disabled rather than deleted, so it is never re-seeded.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Milestone(Base):
    __tablename__ = "deal_milestones"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_date: Mapped[date | None] = mapped_column(Date, default=None)
    # Set when the 3-day reminder went out; cleared when the planned date moves.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class EmergencyAccess(Base):
    """Break-glass (AUTHZ-08): an admin's time-boxed, read-only access to one deal."""

    __tablename__ = "deal_emergency_access"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
