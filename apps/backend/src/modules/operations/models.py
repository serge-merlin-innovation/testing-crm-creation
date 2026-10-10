from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class RecoveryDrill(Base):
    """A logged restore test (NFR-01 c5) or disaster-recovery run (NFR-03 c2), with its measured RPO and RTO."""

    __tablename__ = "recovery_drills"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    backup_taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service_restored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    data_loss_hours: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_hours: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    logged_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SecurityFinding(Base):
    """A penetration-test or scanner finding. High and critical ones must be fixed within 30 days."""

    __tablename__ = "security_findings"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=None)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    overdue_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )


class MaintenanceWindow(Base):
    """Planned downtime, announced to every user at least 48 hours ahead (NFR-03 c3)."""

    __tablename__ = "maintenance_windows"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    announced_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True)
