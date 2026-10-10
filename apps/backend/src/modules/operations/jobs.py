from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .service import OperationsService

OVERDUE_FINDINGS_JOB = "operations.overdue_findings"


async def overdue_findings(db: AsyncSession, now: datetime) -> None:
    await OperationsService(NotificationService(get_email_sender())).notify_overdue(db, now)


def register_jobs() -> None:
    job_runner.register(OVERDUE_FINDINGS_JOB, timedelta(hours=1), overdue_findings)
