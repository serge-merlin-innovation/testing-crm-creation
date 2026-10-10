from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class Activity(Base):
    """A logged call, meeting or email. Deleting sets `deleted_at`; an admin may restore it for 30 days."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    participants: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, index=True)
    deleted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True, default=None
    )


class ActivityLink(Base):
    """One record an activity shows on. `record_id` points at contacts, companies or mandates by `record_type`."""

    __tablename__ = "activity_links"
    __table_args__ = (
        Index("ix_activity_links_unique", "activity_id", "record_type", "record_id", unique=True),
        Index("ix_activity_links_record", "record_type", "record_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)


class Note(Base):
    """A note on a record. Private: author only, admins included. Deal-confidential: deal team only."""

    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_record", "record_type", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(24), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mandate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mandates.id", ondelete="CASCADE"), index=True, default=None
    )
