from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .service import ImportService

IMPORT_JOB = "data_import.run_queued"


async def run_queued_imports(db: AsyncSession, now: datetime) -> None:
    await ImportService(NotificationService(get_email_sender())).run_queued(db, now)


def register_jobs() -> None:
    job_runner.register(IMPORT_JOB, timedelta(minutes=1), run_queued_imports)
