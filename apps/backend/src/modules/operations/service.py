from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.i18n import format_datetime, translate
from ...infrastructure.i18n.formatters import BELGIAN_TIME_ZONE
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ResourceNotFoundError, ValidationError
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..role.permissions import Permission
from ..user.models import User
from .models import MaintenanceWindow, RecoveryDrill, SecurityFinding
from .schemas import DrillCreate, DrillKind, FindingCreate, FindingStatus, MaintenanceCreate, Severity

RPO = timedelta(hours=24)
RTO = timedelta(hours=8)
RESTORE_TEST_EVERY = timedelta(days=92)
FIX_WITHIN = timedelta(days=30)
BLOCKING = (Severity.CRITICAL.value, Severity.HIGH.value)
NOTICE = timedelta(hours=48)
BUSINESS_START = time(8, 0)
BUSINESS_END = time(20, 0)


def _hours(delta: timedelta) -> float:
    return round(delta.total_seconds() / 3600, 2)


def drill_failures(drill: RecoveryDrill) -> list[str]:
    failures = []
    if drill.data_loss_hours > _hours(RPO):
        failures.append("rpo")
    if drill.recovery_hours > _hours(RTO):
        failures.append("rto")
    if not drill.data_verified:
        failures.append("data")
    return failures


def drill_view(drill: RecoveryDrill) -> dict[str, Any]:
    return {**{c: getattr(drill, c) for c in drill.__table__.columns.keys()}, "failures": drill_failures(drill)}


def finding_view(finding: SecurityFinding) -> dict[str, Any]:
    fixed_in_time = None
    if finding.due_at is not None and finding.fixed_at is not None:
        fixed_in_time = finding.fixed_at <= finding.due_at
    return {**{c: getattr(finding, c) for c in finding.__table__.columns.keys()}, "fixed_in_time": fixed_in_time}


def touches_business_hours(starts_at: datetime, ends_at: datetime) -> bool:
    """True when any minute of the window falls in 8:00-20:00 Brussels time on a weekday."""
    start = starts_at.astimezone(BELGIAN_TIME_ZONE)
    end = ends_at.astimezone(BELGIAN_TIME_ZONE)
    day = start.date()
    while day <= end.date():
        if day.weekday() < 5:
            open_at = datetime.combine(day, BUSINESS_START, BELGIAN_TIME_ZONE)
            close_at = datetime.combine(day, BUSINESS_END, BELGIAN_TIME_ZONE)
            if start < close_at and end > open_at:
                return True
        day += timedelta(days=1)
    return False


async def _active_users(db: AsyncSession) -> list[User]:
    rows = await db.execute(select(User).where(User.is_deleted.is_(False), User.role_id.is_not(None)))
    return list(rows.scalars())


class OperationsService:
    def __init__(self, notifications: NotificationService, audit: AuditService | None = None) -> None:
        self.notifications = notifications
        self.audit = audit or AuditService()

    async def log_drill(
        self, db: AsyncSession, user: dict[str, Any], values: DrillCreate, context: AuditContext
    ) -> dict[str, Any]:
        if values.service_restored_at < values.started_at:
            raise ValidationError("The service cannot be back before the recovery started.", field="service_restored_at")
        drill = RecoveryDrill(
            kind=values.kind.value,
            backup_taken_at=values.backup_taken_at,
            started_at=values.started_at,
            service_restored_at=values.service_restored_at,
            data_verified=values.data_verified,
            data_loss_hours=_hours(values.started_at - values.backup_taken_at),
            recovery_hours=_hours(values.service_restored_at - values.started_at),
            passed=False,
            logged_at=context.clock.now(),
            logged_by=user["id"],
            notes=values.notes.strip(),
        )
        drill.passed = not drill_failures(drill)
        db.add(drill)
        await db.flush()
        self.audit.record(
            db,
            context,
            "recovery_drill.logged",
            record_type="recovery_drill",
            record_id=drill.id,
            new_values={
                "kind": drill.kind,
                "passed": drill.passed,
                "rpo_hours": drill.data_loss_hours,
                "rto_hours": drill.recovery_hours,
            },
        )
        await db.commit()
        return drill_view(drill)

    async def drills(self, db: AsyncSession) -> list[dict[str, Any]]:
        rows = await db.execute(select(RecoveryDrill).order_by(RecoveryDrill.logged_at.desc()).limit(100))
        return [drill_view(drill) for drill in rows.scalars()]

    async def drill_status(self, db: AsyncSession, now: datetime) -> dict[str, Any]:
        last = (
            await db.execute(
                select(func.max(RecoveryDrill.logged_at)).where(
                    RecoveryDrill.passed.is_(True), RecoveryDrill.kind == DrillKind.RESTORE_TEST.value
                )
            )
        ).scalar_one_or_none()
        return {
            "restore_test_due": last is None or now - last > RESTORE_TEST_EVERY,
            "last_passed_at": last,
            "rpo_hours": int(_hours(RPO)),
            "rto_hours": int(_hours(RTO)),
        }

    async def add_finding(
        self, db: AsyncSession, user: dict[str, Any], values: FindingCreate, context: AuditContext
    ) -> dict[str, Any]:
        reported_at = values.reported_at or context.clock.now()
        finding = SecurityFinding(
            source=values.source.value,
            severity=values.severity.value,
            title=values.title.strip(),
            reference=values.reference.strip(),
            reported_at=reported_at,
            due_at=reported_at + FIX_WITHIN if values.severity.value in BLOCKING else None,
            created_by=user["id"],
        )
        db.add(finding)
        await db.flush()
        self.audit.record(
            db,
            context,
            "security_finding.created",
            record_type="security_finding",
            record_id=finding.id,
            new_values={"severity": finding.severity, "source": finding.source, "title": finding.title},
        )
        await db.commit()
        return finding_view(finding)

    async def update_finding(
        self, db: AsyncSession, finding_id: int, status: FindingStatus, context: AuditContext
    ) -> dict[str, Any]:
        finding = await db.get(SecurityFinding, finding_id)
        if finding is None:
            raise ResourceNotFoundError("Finding not found")
        old = finding.status
        finding.status = status.value
        finding.fixed_at = context.clock.now() if status == FindingStatus.FIXED else None
        self.audit.record(
            db,
            context,
            "security_finding.updated",
            record_type="security_finding",
            record_id=finding.id,
            old_values={"status": old},
            new_values={"status": finding.status},
        )
        await db.commit()
        return finding_view(finding)

    async def findings(self, db: AsyncSession) -> list[dict[str, Any]]:
        rows = await db.execute(select(SecurityFinding).order_by(SecurityFinding.reported_at.desc()).limit(500))
        return [finding_view(finding) for finding in rows.scalars()]

    async def release_gate(self, db: AsyncSession, now: datetime) -> dict[str, Any]:
        open_blocking = list(
            (
                await db.execute(
                    select(SecurityFinding).where(
                        SecurityFinding.status == FindingStatus.OPEN.value, SecurityFinding.severity.in_(BLOCKING)
                    )
                )
            ).scalars()
        )
        overdue = [finding for finding in open_blocking if finding.due_at is not None and finding.due_at < now]
        return {"releasable": not open_blocking, "open_blocking": len(open_blocking), "overdue": len(overdue)}

    async def notify_overdue(self, db: AsyncSession, now: datetime) -> None:
        overdue = list(
            (
                await db.execute(
                    select(SecurityFinding).where(
                        SecurityFinding.status == FindingStatus.OPEN.value,
                        SecurityFinding.due_at < now,
                        SecurityFinding.overdue_notified_at.is_(None),
                    )
                )
            ).scalars()
        )
        if not overdue:
            return
        recipients = [
            user
            for user in await _active_users(db)
            if {Permission.SETTINGS_MANAGE.value, Permission.AUDIT_READ.value} & set(user.permissions or [])
        ]
        for finding in overdue:
            for user in recipients:
                await self.notifications.add(
                    db,
                    Message(
                        user_id=user.id,
                        email=user.email,
                        kind=EventKind.SECURITY_FINDING_OVERDUE.value,
                        title=translate("security.finding_overdue.title", user.language, severity=finding.severity),
                        body=translate(
                            "security.finding_overdue.body",
                            user.language,
                            title=finding.title,
                            due=format_datetime(finding.due_at) if finding.due_at else "",
                        ),
                        link="/operations",
                    ),
                    now,
                )
            finding.overdue_notified_at = now
        await db.commit()
        await self.notifications.flush_emails()

    async def announce(
        self, db: AsyncSession, user: dict[str, Any], values: MaintenanceCreate, context: AuditContext
    ) -> dict[str, Any]:
        now = context.clock.now()
        if values.ends_at <= values.starts_at:
            raise ValidationError("The window must end after it starts.", field="ends_at")
        if values.starts_at - now < NOTICE:
            raise ValidationError("Announce maintenance at least 48 hours before it starts.", field="starts_at")
        if touches_business_hours(values.starts_at, values.ends_at):
            raise ValidationError(
                "Maintenance must run outside business hours (8:00-20:00 Brussels time, Monday to Friday).",
                field="starts_at",
            )
        window = MaintenanceWindow(
            starts_at=values.starts_at,
            ends_at=values.ends_at,
            reason=values.reason.strip(),
            announced_at=now,
            announced_by=user["id"],
        )
        db.add(window)
        await db.flush()
        for recipient in await _active_users(db):
            await self.notifications.add(
                db,
                Message(
                    user_id=recipient.id,
                    email=recipient.email,
                    kind=EventKind.MAINTENANCE_SCHEDULED.value,
                    title=translate("maintenance.scheduled.title", recipient.language, start=format_datetime(window.starts_at)),
                    body=translate(
                        "maintenance.scheduled.body",
                        recipient.language,
                        start=format_datetime(window.starts_at),
                        end=format_datetime(window.ends_at),
                        reason=window.reason,
                    ),
                ),
                now,
            )
        self.audit.record(
            db,
            context,
            "maintenance.scheduled",
            record_type="maintenance_window",
            record_id=window.id,
            new_values={
                "starts_at": window.starts_at.isoformat(),
                "ends_at": window.ends_at.isoformat(),
                "reason": window.reason,
            },
        )
        await db.commit()
        await self.notifications.flush_emails()
        return {c: getattr(window, c) for c in window.__table__.columns.keys()}

    async def upcoming(self, db: AsyncSession, now: datetime) -> list[MaintenanceWindow]:
        rows = await db.execute(
            select(MaintenanceWindow).where(MaintenanceWindow.ends_at > now).order_by(MaintenanceWindow.starts_at)
        )
        return list(rows.scalars())
