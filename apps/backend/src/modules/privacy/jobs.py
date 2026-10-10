from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .service import PrivacyService

RETENTION_JOB = "privacy.retention_review"
MONTHLY = timedelta(days=30)


async def retention_review(db: AsyncSession, now: datetime) -> None:
    await PrivacyService(NotificationService(get_email_sender())).ask_owners(db, now)


def register_jobs() -> None:
    job_runner.register(RETENTION_JOB, MONTHLY, retention_review)
