from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    assignee_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recurrence: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_type: Mapped[str | None] = mapped_column(String(16), default=None)
    record_id: Mapped[int | None] = mapped_column(Integer, default=None)
    # Set when the linked record is a deal: only its team may hold or see the task.
    mandate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mandates.id", ondelete="CASCADE"), index=True, default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TaskDigest(Base):
    """One row per assignee per day the overdue digest went out, so a rerun never sends twice."""

    __tablename__ = "task_digests"
    __table_args__ = (Index("ix_task_digests_unique", "user_id", "day", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
