from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .service import AccessService

ACCESS_JOB = "access.quarterly_review"


async def run_access_jobs(db: AsyncSession, now: datetime, notifications: NotificationService | None = None) -> None:
    """Opens the quarter's team reviews (ADM-05 c1) and escalates those left unanswered for 14 days (c2)."""
    service = AccessService(notifications or NotificationService(get_email_sender()))
    await service.open_quarterly_reviews(db, now)
    await service.escalate_overdue_reviews(db, now)


async def access_reviews(db: AsyncSession, now: datetime) -> None:
    await run_access_jobs(db, now)


def register_jobs() -> None:
    job_runner.register(ACCESS_JOB, timedelta(hours=1), access_reviews)
