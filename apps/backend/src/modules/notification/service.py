from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Notification
from .ports import EmailSender, SentEmail


@dataclass(frozen=True)
class Message:
    user_id: int
    email: str
    kind: str
    title: str
    body: str
    link: str | None = None
    mandate_id: int | None = None


class NotificationService:
    """In-app row plus an email. Deal messages carry the code name only, never client or target."""

    def __init__(self, sender: EmailSender) -> None:
        self.sender = sender
        self._outbox: list[SentEmail] = []

    def add(self, db: AsyncSession, message: Message, now: datetime) -> None:
        db.add(
            Notification(
                user_id=message.user_id,
                kind=message.kind,
                title=message.title,
                body=message.body,
                created_at=now,
                link=message.link,
                mandate_id=message.mandate_id,
            )
        )
        self._outbox.append(SentEmail(to=message.email, subject=message.title, body=message.body))

    async def flush_emails(self) -> None:
        """Call after the commit, so a rolled-back change never emails anyone."""
        outbox, self._outbox = self._outbox, []
        for email in outbox:
            await self.sender.send(email)

    async def list_for(
        self, db: AsyncSession, user_id: int, visible_mandate_ids: Collection[int], limit: int = 50
    ) -> list[Notification]:
        query = (
            select(Notification)
            .where(
                Notification.user_id == user_id,
                or_(Notification.mandate_id.is_(None), Notification.mandate_id.in_(list(visible_mandate_ids))),
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
        return list((await db.execute(query)).scalars())
