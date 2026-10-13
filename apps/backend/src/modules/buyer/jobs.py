from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.email import get_email_sender
from ...infrastructure.jobs import job_runner
from ..notification.service import NotificationService
from .service import BuyerReminders

BUYER_JOB = "buyers.reminders"


async def run_buyer_jobs(db: AsyncSession, now: datetime, notifications: NotificationService | None = None) -> None:
    """Buyers idle 14 days in an active phase (BUY-03 c5) and NDAs pending over 10 days (BUY-04 c2)."""
    await BuyerReminders(notifications or NotificationService(get_email_sender())).run(db, now)


async def buyer_reminders(db: AsyncSession, now: datetime) -> None:
    await run_buyer_jobs(db, now)


def register_jobs() -> None:
    job_runner.register(BUYER_JOB, timedelta(hours=1), buyer_reminders)
