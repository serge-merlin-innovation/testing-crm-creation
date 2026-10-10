"""The private iCal feed (ACT-05). Every deal-linked event carries the code name only (AUTHZ-02 c3)."""

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import settings
from ..activity.models import Activity, ActivityLink
from ..activity.schemas import ActivityType, RecordType
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ResourceNotFoundError
from ..mandate.models import DealTeamMember, Mandate, Milestone
from ..task.models import Task
from ..user.models import User
from .models import CalendarFeed

FEED_PATH = "/api/v1/calendar-feed/ics/"
MEETING_LENGTH = timedelta(hours=1)
# How far back the feed reaches, so a calendar app is not handed years of history.
HISTORY = timedelta(days=90)


class CalendarFeedNotFoundError(ResourceNotFoundError):
    pass


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def fold(line: str) -> list[str]:
    """RFC 5545 3.1: lines longer than 75 octets continue on the next line after a space."""
    raw = line.encode()
    if len(raw) <= 75:
        return [line]
    parts: list[str] = []
    while raw:
        size = 75 if not parts else 74
        cut = min(size, len(raw))
        while cut < len(raw) and (raw[cut] & 0xC0) == 0x80:
            cut -= 1
        parts.append(("" if not parts else " ") + raw[:cut].decode())
        raw = raw[cut:]
    return parts


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def event(uid: str, summary: str, now: datetime, *, at: datetime | None = None, day: date | None = None) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{uid}@crm", f"DTSTAMP:{stamp(now)}"]
    if at is not None:
        lines += [f"DTSTART:{stamp(at)}", f"DTEND:{stamp(at + MEETING_LENGTH)}"]
    elif day is not None:
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    lines += [f"SUMMARY:{escape(summary)}", "CLASS:PRIVATE", "END:VEVENT"]
    return lines


class CalendarFeedService:
    @staticmethod
    def url(token: str) -> str:
        return f"{settings.APP_URL}{FEED_PATH}{token}.ics"

    async def _feed(self, db: AsyncSession, user_id: int) -> CalendarFeed | None:
        return (await db.execute(select(CalendarFeed).where(CalendarFeed.user_id == user_id))).scalar_one_or_none()

    async def get_or_create(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> CalendarFeed:
        feed = await self._feed(db, user["id"])
        if feed is None:
            feed = CalendarFeed(user_id=user["id"], token=secrets.token_urlsafe(32), created_at=now)
            db.add(feed)
            await db.commit()
        return feed

    async def regenerate(self, db: AsyncSession, user: dict[str, Any], now: datetime, context: AuditContext) -> CalendarFeed:
        feed = await self.get_or_create(db, user, now)
        feed.token = secrets.token_urlsafe(32)
        feed.created_at = now
        AuditService().record(db, context, "calendar_feed.regenerated", record_type="calendar_feed", record_id=feed.id)
        await db.commit()
        return feed

    async def render(self, db: AsyncSession, token: str, now: datetime) -> str:
        feed = (await db.execute(select(CalendarFeed).where(CalendarFeed.token == token))).scalar_one_or_none()
        if feed is None:
            raise CalendarFeedNotFoundError("Unknown calendar feed")
        owner = await db.get(User, feed.user_id)
        if owner is None or owner.is_deleted:
            raise CalendarFeedNotFoundError("Unknown calendar feed")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CRM//Calendar feed//EN", "CALSCALE:GREGORIAN"]
        lines += ["X-WR-CALNAME:CRM", "METHOD:PUBLISH"]
        for item in await self._events(db, feed.user_id, now):
            lines += item
        lines.append("END:VCALENDAR")
        return "".join(part + "\r\n" for line in lines for part in fold(line))

    async def _events(self, db: AsyncSession, user_id: int, now: datetime) -> list[list[str]]:
        since = now - HISTORY
        meetings = list(
            (
                await db.execute(
                    select(Activity)
                    .where(
                        Activity.author_id == user_id,
                        Activity.type == ActivityType.MEETING.value,
                        Activity.deleted_at.is_(None),
                        Activity.occurred_at >= since,
                    )
                    .order_by(Activity.occurred_at, Activity.id)
                )
            ).scalars()
        )
        meeting_deals: dict[int, int] = {}
        if meetings:
            rows = await db.execute(
                select(ActivityLink.activity_id, ActivityLink.record_id).where(
                    ActivityLink.activity_id.in_([m.id for m in meetings]),
                    ActivityLink.record_type == RecordType.MANDATE.value,
                )
            )
            for activity_id, mandate_id in rows.tuples():
                meeting_deals.setdefault(activity_id, mandate_id)
        tasks = list(
            (
                await db.execute(
                    select(Task)
                    .where(Task.assignee_id == user_id, Task.completed_at.is_(None), Task.due_date >= since.date())
                    .order_by(Task.due_date, Task.id)
                )
            ).scalars()
        )
        active = (DealTeamMember.expires_at.is_(None)) | (DealTeamMember.expires_at > now)
        staffed = select(DealTeamMember.mandate_id).where(DealTeamMember.user_id == user_id, active)
        milestones = list(
            (
                await db.execute(
                    select(Milestone)
                    .join(Mandate, Mandate.id == Milestone.mandate_id)
                    .where(
                        Milestone.mandate_id.in_(staffed),
                        Mandate.closed_at.is_(None),
                        Milestone.planned_date >= since.date(),
                    )
                    .order_by(Milestone.planned_date, Milestone.id)
                )
            ).scalars()
        )
        mandate_ids = (
            set(meeting_deals.values()) | {t.mandate_id for t in tasks if t.mandate_id} | {m.mandate_id for m in milestones}
        )
        code_names: dict[int, str] = {}
        if mandate_ids:
            code_names = dict(
                list((await db.execute(select(Mandate.id, Mandate.code_name).where(Mandate.id.in_(mandate_ids)))).tuples())
            )

        events: list[list[str]] = []
        for meeting in meetings:
            deal = meeting_deals.get(meeting.id)
            summary = (
                f"Meeting: {code_names[deal]}" if deal else "Meeting: " + (meeting.note.strip().splitlines() or [""])[0][:200]
            )
            events.append(event(f"meeting-{meeting.id}", summary, now, at=meeting.occurred_at))
        for task in tasks:
            summary = f"Task: {code_names[task.mandate_id]}" if task.mandate_id else f"Task: {task.title}"
            events.append(event(f"task-{task.id}", summary, now, day=task.due_date))
        for milestone in milestones:
            events.append(
                event(
                    f"milestone-{milestone.id}",
                    f"Milestone: {code_names[milestone.mandate_id]}",
                    now,
                    day=milestone.planned_date,
                )
            )
        return events
