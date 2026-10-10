from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.email import get_email_sender
from ...infrastructure.jobs import job_runner
from ..notification.service import NotificationService
from .service import OriginationService

ORIGINATION_JOB = "origination.reminders"


async def run_origination_jobs(db: AsyncSession, now: datetime, notifications: NotificationService | None = None) -> None:
    """On-hold revisit dates (ORI-03 c3) and dormant prospects (ORI-04)."""
    service = OriginationService(notifications or NotificationService(get_email_sender()))
    await service.create_revisit_tasks(db, now)
    await service.create_dormant_tasks(db, now)


async def origination_reminders(db: AsyncSession, now: datetime) -> None:
    await run_origination_jobs(db, now)


def register_jobs() -> None:
    job_runner.register(ORIGINATION_JOB, timedelta(hours=1), origination_reminders)
