import calendar
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity.schemas import RecordRef, RecordType
from ..activity.service import require_record
from ..common.exceptions import PermissionDeniedError, TaskNotFoundError, ValidationError
from ..mandate.models import DealTeamMember, Mandate
from ..mandate.policy import DealAction, DealPolicy
from ..notification.schemas import EventKind
from ..notification.service import Message, NotificationService
from ..user.models import User
from .models import Task, TaskDigest
from .schemas import Recurrence, TaskCreate


def next_due(due: date, recurrence: Recurrence) -> date | None:
    if recurrence == Recurrence.DAILY:
        return due + timedelta(days=1)
    if recurrence == Recurrence.WEEKLY:
        return due + timedelta(weeks=1)
    if recurrence == Recurrence.MONTHLY:
        year, month = (due.year + 1, 1) if due.month == 12 else (due.year, due.month + 1)
        return due.replace(year=year, month=month, day=min(due.day, calendar.monthrange(year, month)[1]))
    return None


def read(task: Task, today: date) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "assignee_id": task.assignee_id,
        "created_by": task.created_by,
        "due_date": task.due_date,
        "recurrence": task.recurrence,
        "record_type": task.record_type,
        "record_id": task.record_id,
        "mandate_id": task.mandate_id,
        "completed_at": task.completed_at,
        "overdue": task.completed_at is None and task.due_date < today,
    }


class TaskService:
    """Tasks for users. Other modules create tasks through `create`, so the deal-team rule always holds."""

    def __init__(self, notifications: NotificationService) -> None:
        self.notifications = notifications

    async def _assignable(self, db: AsyncSession, assignee: User, mandate_id: int, now: datetime) -> bool:
        member = (
            await db.execute(
                select(DealTeamMember.id).where(
                    DealTeamMember.mandate_id == mandate_id,
                    DealTeamMember.user_id == assignee.id,
                    or_(DealTeamMember.expires_at.is_(None), DealTeamMember.expires_at > now),
                )
            )
        ).first()
        return member is not None

    async def create(self, db: AsyncSession, user: dict[str, Any], values: TaskCreate, now: datetime) -> dict[str, Any]:
        if (values.record_type is None) != (values.record_id is None):
            raise ValidationError("Give both the record type and id, or neither", field="record_id")
        mandate_id = None
        if values.record_type is not None and values.record_id is not None:
            await require_record(
                db, user, RecordRef(record_type=values.record_type, record_id=values.record_id), now, DealAction.EDIT
            )
            if values.record_type == RecordType.MANDATE:
                mandate_id = values.record_id
        assignee = await db.get(User, values.assignee_id)
        if assignee is None or assignee.is_deleted:
            raise ValidationError("Unknown assignee", field="assignee_id")
        if mandate_id is not None and not await self._assignable(db, assignee, mandate_id, now):
            raise ValidationError("A deal task can only go to someone on the deal team", field="assignee_id")
        task = Task(
            title=values.title.strip(),
            assignee_id=assignee.id,
            created_by=user["id"],
            due_date=values.due_date,
            recurrence=values.recurrence.value,
            created_at=now,
            record_type=values.record_type.value if values.record_type else None,
            record_id=values.record_id,
            mandate_id=mandate_id,
        )
        db.add(task)
        await db.flush()
        if assignee.id != user["id"]:
            await self.notifications.add(db, await self._assigned_message(db, task, assignee), now)
        await db.commit()
        await self.notifications.flush_emails()
        return read(task, now.date())

    async def _assigned_message(self, db: AsyncSession, task: Task, assignee: User) -> Message:
        due = task.due_date.isoformat()
        if task.mandate_id is not None:
            # Deal messages name the code name only: the task title is free text and may name the client.
            code_name = (await db.execute(select(Mandate.code_name).where(Mandate.id == task.mandate_id))).scalar_one()
            title, body = f"New task on {code_name}", f"You have a new task on {code_name}, due {due}."
        else:
            title, body = f"New task: {task.title}", f"{task.title}, due {due}."
        return Message(
            user_id=assignee.id,
            email=assignee.email,
            kind=EventKind.TASK_ASSIGNED.value,
            title=title,
            body=body,
            link="/tasks",
            mandate_id=task.mandate_id,
        )

    async def mine(self, db: AsyncSession, user: dict[str, Any], now: datetime, include_done: bool) -> list[dict[str, Any]]:
        visible = await DealPolicy(now).visible_mandate_ids(db, user)
        query = (
            select(Task)
            .where(Task.assignee_id == user["id"], or_(Task.mandate_id.is_(None), Task.mandate_id.in_(visible)))
            .order_by(Task.due_date, Task.id)
        )
        if not include_done:
            query = query.where(Task.completed_at.is_(None))
        return [read(task, now.date()) for task in (await db.execute(query)).scalars()]

    async def complete(self, db: AsyncSession, user: dict[str, Any], task_id: int, now: datetime) -> dict[str, Any]:
        task = await db.get(Task, task_id)
        visible = await DealPolicy(now).visible_mandate_ids(db, user)
        if task is None or (task.mandate_id is not None and task.mandate_id not in visible):
            raise TaskNotFoundError(f"Task {task_id} not found")
        if user["id"] not in (task.assignee_id, task.created_by):
            raise PermissionDeniedError("Only the assignee or creator completes a task")
        if task.completed_at is None:
            task.completed_at = now
            due = next_due(task.due_date, Recurrence(task.recurrence))
            if due is not None:
                db.add(
                    Task(
                        title=task.title,
                        assignee_id=task.assignee_id,
                        created_by=task.created_by,
                        due_date=due,
                        recurrence=task.recurrence,
                        created_at=now,
                        record_type=task.record_type,
                        record_id=task.record_id,
                        mandate_id=task.mandate_id,
                    )
                )
            await db.commit()
        return read(task, now.date())

    async def send_overdue_digests(self, db: AsyncSession, now: datetime) -> None:
        """Daily job: one digest per assignee with overdue open tasks, at most once a day."""
        today = now.date()
        overdue = list(
            (
                await db.execute(
                    select(Task).where(Task.completed_at.is_(None), Task.due_date < today).order_by(Task.due_date, Task.id)
                )
            ).scalars()
        )
        by_user: dict[int, list[Task]] = {}
        for task in overdue:
            by_user.setdefault(task.assignee_id, []).append(task)
        already = set(
            (
                await db.execute(select(TaskDigest.user_id).where(TaskDigest.day == today, TaskDigest.user_id.in_(by_user)))
            ).scalars()
        )
        code_names = dict(
            list(
                (
                    await db.execute(
                        select(Mandate.id, Mandate.code_name).where(
                            Mandate.id.in_({t.mandate_id for t in overdue if t.mandate_id})
                        )
                    )
                ).tuples()
            )
        )
        for user_id, tasks in by_user.items():
            if user_id in already:
                continue
            assignee = await db.get(User, user_id)
            if assignee is None or assignee.is_deleted:
                continue
            lines = [
                f"- {code_names[t.mandate_id] + ' task' if t.mandate_id else t.title}, due {t.due_date.isoformat()}"
                for t in tasks
            ]
            await self.notifications.add(
                db,
                Message(
                    user_id=user_id,
                    email=assignee.email,
                    kind=EventKind.TASK_OVERDUE_DIGEST.value,
                    title="You have 1 overdue task" if len(tasks) == 1 else f"You have {len(tasks)} overdue tasks",
                    body="\n".join(lines),
                    link="/tasks",
                ),
                now,
            )
            db.add(TaskDigest(user_id=user_id, day=today))
        await db.commit()
        await self.notifications.flush_emails()
