from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class DataImport(Base):
    """One uploaded spreadsheet, from upload through preview to the finished import.

    `rows` holds the sheet as read; `results` holds one status per row once previewed or imported,
    which is also what the error file is built from.
    """

    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    entity: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    headers: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rows: Mapped[list[list[Any]]] = mapped_column(JSON, nullable=False)
    # uploaded -> queued (background) -> completed
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mapping: Mapped[dict[str, str] | None] = mapped_column(JSON, default=None)
    results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
