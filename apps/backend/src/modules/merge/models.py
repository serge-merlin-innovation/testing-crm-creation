from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class RecordMerge(Base):
    """Everything needed to undo a merge: the deleted duplicate, the survivor's replaced values, and
    which rows moved or were dropped as already present on the survivor."""

    __tablename__ = "record_merges"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    record_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # No foreign keys: the duplicate no longer exists, and an undone merge must still read back.
    survivor_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duplicate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    merged_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duplicate_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    survivor_before: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    moved: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dropped: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    undone_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True, default=None)
