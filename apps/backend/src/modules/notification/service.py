from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.i18n.localize import localize
from ..user.models import User
from .models import Notification, NotificationPreference
from .ports import EmailSender, SentEmail
from .schemas import DEFAULT_CHANNEL, Channel, EventKind


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
    """In-app row and/or email, per the recipient's channel for the event kind.

    Deal messages carry the code name only, never client or target.
    """

    def __init__(self, sender: EmailSender) -> None:
        self.sender = sender
        self._outbox: list[SentEmail] = []

    async def channel(self, db: AsyncSession, user_id: int, kind: str) -> Channel:
        stored = (
            await db.execute(
                select(NotificationPreference.channel).where(
                    NotificationPreference.user_id == user_id, NotificationPreference.kind == kind
                )
            )
        ).scalar_one_or_none()
        return Channel(stored) if stored else DEFAULT_CHANNEL

    async def add(self, db: AsyncSession, message: Message, now: datetime) -> None:
        channel = await self.channel(db, message.user_id, message.kind)
        # Written in English at the call site; stored and sent in the recipient's language (NFR-04).
        language = (await db.execute(select(User.language).where(User.id == message.user_id))).scalar_one_or_none()
        message = replace(message, title=localize(message.title, language), body=localize(message.body, language))
        if channel in (Channel.IN_APP, Channel.BOTH):
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
        if channel in (Channel.EMAIL, Channel.BOTH):
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

    async def preferences(self, db: AsyncSession, user_id: int) -> list[dict[str, str]]:
        rows = await db.execute(
            select(NotificationPreference.kind, NotificationPreference.channel).where(NotificationPreference.user_id == user_id)
        )
        stored = {kind: channel for kind, channel in rows.tuples()}
        return [{"kind": kind.value, "channel": stored.get(kind.value, DEFAULT_CHANNEL.value)} for kind in EventKind]

    async def set_preferences(self, db: AsyncSession, user_id: int, choices: dict[EventKind, Channel]) -> list[dict[str, str]]:
        existing = {
            row.kind: row
            for row in (
                await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
            ).scalars()
        }
        for kind, channel in choices.items():
            if kind.value in existing:
                existing[kind.value].channel = channel.value
            else:
                db.add(NotificationPreference(user_id=user_id, kind=kind.value, channel=channel.value))
        await db.commit()
        return await self.preferences(db, user_id)
