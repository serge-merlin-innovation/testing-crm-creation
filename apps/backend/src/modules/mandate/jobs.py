from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.jobs import job_runner
from ..notification.dependencies import get_email_sender
from ..notification.service import NotificationService
from .pipeline import PipelineService

MILESTONE_JOB = "deals.milestone_reminders"


async def notify_due_milestones(db: AsyncSession, now: datetime, notifications: NotificationService | None = None) -> None:
    await PipelineService(notifications or NotificationService(get_email_sender())).remind_due_milestones(db, now)


async def milestone_reminders(db: AsyncSession, now: datetime) -> None:
    await notify_due_milestones(db, now)


def register_jobs() -> None:
    job_runner.register(MILESTONE_JOB, timedelta(hours=1), milestone_reminders)
