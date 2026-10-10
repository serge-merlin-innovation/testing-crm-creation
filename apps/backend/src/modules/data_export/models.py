from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class ExportApproval(Base):
    """An analyst's request to export more rows than their role may alone, and a partner's answer.

    Approves one export of exactly `filter`, used once."""

    __tablename__ = "export_approvals"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    requested_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    filter: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
