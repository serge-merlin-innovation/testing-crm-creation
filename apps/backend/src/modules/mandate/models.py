from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
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
