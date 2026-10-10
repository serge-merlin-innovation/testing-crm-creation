from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .service import ConflictService, KycService

COMPLIANCE_JOB = "compliance.reminders"


async def run_compliance_jobs(db: AsyncSession, now: datetime, notifications: NotificationService | None = None) -> None:
    """Conflict reviews waiting 5 working days (AUTHZ-05 c5) and KYC older than 12 months (ORI-05 c3)."""
    await ConflictService(notifications or NotificationService(get_email_sender())).remind_overdue_reviews(db, now)
    await KycService().create_refresh_tasks(db, now)


async def compliance_reminders(db: AsyncSession, now: datetime) -> None:
    await run_compliance_jobs(db, now)


def register_jobs() -> None:
    job_runner.register(COMPLIANCE_JOB, timedelta(hours=1), compliance_reminders)
