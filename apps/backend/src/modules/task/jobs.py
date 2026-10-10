from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .service import TaskService

DIGEST_JOB = "tasks.overdue_digest"


async def overdue_digest(db: AsyncSession, now: datetime) -> None:
    await TaskService(NotificationService(get_email_sender())).send_overdue_digests(db, now)


def register_jobs() -> None:
    # Hourly tick; the digest itself goes out once per user per day, on the first run of the day.
    job_runner.register(DIGEST_JOB, timedelta(hours=1), overdue_digest)
