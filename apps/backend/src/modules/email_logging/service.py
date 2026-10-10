import re
import secrets
from dataclasses import replace
from datetime import datetime
from email.utils import getaddresses
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.config.settings import settings
from ..activity.models import Activity, ActivityLink
from ..activity.schemas import ActivityCreate, ActivityType, RecordRef, RecordType
from ..activity.service import ActivityService
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ContactNotFoundError, DomainError, PermissionDeniedError, ResourceNotFoundError
from ..contact.models import Contact
from ..mandate.models import Mandate
from ..mandate.policy import DealAction, DealPolicy
from ..role.authorization import has_record_access
from ..user.crud import crud_users
from ..user.models import User
from ..user.schemas import UserRead
from .models import LoggedEmail, LoggingAddress, UnmatchedEmail
from .schemas import InboundEmail, InboundResult, InboundStatus, UnmatchedLink

CODE_NAME_TAG = re.compile(r"\[([^\[\]]{1,100})\]")
# Header lines a mail client copies into the body when forwarding: the original correspondents.
FORWARDED_HEADER = re.compile(r"^\s*>?\s*(?:From|To|Cc|De|Van|Aan|À|A)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
NOTE_LIMIT = 20000


class UnknownSenderError(PermissionDeniedError):
    """The sender is not a CRM user, or did not write to their own logging address (ACT-04 c2)."""


class UnmatchedEmailNotFoundError(ResourceNotFoundError):
    pass


def addresses(values: list[str]) -> list[str]:
    found = [address.strip().lower() for _, address in getaddresses(values) if "@" in address]
    return list(dict.fromkeys(found))


def note_for(subject: str, body: str, attachment_names: list[str]) -> str:
    parts = [subject or "(no subject)"]
    if body.strip():
        parts.append(body.strip())
    if attachment_names:
        parts.append("Attachments: " + ", ".join(attachment_names))
    note = "\n\n".join(parts)
    return note if len(note) <= NOTE_LIMIT else note[: NOTE_LIMIT - 1] + "…"


class EmailLoggingService:
    def __init__(self, activities: ActivityService | None = None, audit: AuditService | None = None) -> None:
        self.activities = activities or ActivityService()
        self.audit = audit or AuditService()

    @staticmethod
    def address(token: str) -> str:
        return f"{token}@{settings.INBOUND_EMAIL_DOMAIN}"

    async def address_for(self, db: AsyncSession, user: dict[str, Any], now: datetime) -> str:
        row = (await db.execute(select(LoggingAddress).where(LoggingAddress.user_id == user["id"]))).scalar_one_or_none()
        if row is None:
            row = LoggingAddress(user_id=user["id"], token=f"log-{secrets.token_hex(16)}", created_at=now)
            db.add(row)
            await db.commit()
        return self.address(row.token)

    async def _sender(self, db: AsyncSession, email: InboundEmail) -> dict[str, Any]:
        if (email.spf or "").lower() != "pass" or (email.dkim or "").lower() != "pass":
            raise UnknownSenderError("Sender not authenticated by SPF and DKIM")
        sender = addresses([email.sender])
        if not sender:
            raise UnknownSenderError("No sender address")
        user = await crud_users.get(db=db, email=sender[0], is_deleted=False, schema_to_select=UserRead)
        if user is None:
            raw = (
                await db.execute(select(User.id).where(func.lower(User.email) == sender[0], User.is_deleted.is_(False)))
            ).scalar_one_or_none()
            user = await crud_users.get(db=db, id=raw, schema_to_select=UserRead) if raw is not None else None
        if user is None:
            raise UnknownSenderError("Sender is not a CRM user")
        if not has_record_access(user):
            raise UnknownSenderError("Sender's role does not log records")
        recipients = addresses(email.to + email.cc + email.bcc)
        domain = "@" + settings.INBOUND_EMAIL_DOMAIN.lower()
        tokens = [address.removesuffix(domain) for address in recipients if address.endswith(domain)]
        owner = (await db.execute(select(LoggingAddress.user_id).where(LoggingAddress.token.in_(tokens)))).scalars().first()
        if owner != user["id"]:
            raise UnknownSenderError("Not sent to the sender's own logging address")
        return user

    @staticmethod
    def _correspondents(email: InboundEmail, user_email: str) -> list[str]:
        forwarded = [match.group(1) for match in FORWARDED_HEADER.finditer(email.text)]
        domain = "@" + settings.INBOUND_EMAIL_DOMAIN.lower()
        every = addresses([email.sender, *email.to, *email.cc, *email.bcc, *forwarded])
        return [address for address in every if not address.endswith(domain) and address != user_email.lower()]

    async def _deal(self, db: AsyncSession, user: dict[str, Any], subject: str, now: datetime) -> int | None:
        """The deal named in the subject, only if the user may log against it (ACT-04 c4)."""
        for tag in CODE_NAME_TAG.findall(subject):
            mandate_id = (
                await db.execute(select(Mandate.id).where(Mandate.code_name_key == tag.strip().lower()))
            ).scalar_one_or_none()
            if mandate_id is None:
                continue
            try:
                await DealPolicy(now).authorize(db, user, mandate_id, DealAction.EDIT)
            except DomainError:
                continue
            return mandate_id
        return None

    async def receive(self, db: AsyncSession, email: InboundEmail, now: datetime, context: AuditContext) -> InboundResult:
        user = await self._sender(db, email)
        # The webhook carries no session: the change is the sender's, so the log names them.
        context = replace(context, user_id=user["id"])
        message_id = (email.message_id or f"<{secrets.token_hex(16)}@crm>").strip()[:255]
        existing = (
            await db.execute(
                select(LoggedEmail.activity_id).where(LoggedEmail.user_id == user["id"], LoggedEmail.message_id == message_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return InboundResult(status=InboundStatus.LOGGED, activity_id=existing)
        pending = (
            await db.execute(
                select(UnmatchedEmail.id).where(UnmatchedEmail.user_id == user["id"], UnmatchedEmail.message_id == message_id)
            )
        ).scalar_one_or_none()
        if pending is not None:
            return InboundResult(status=InboundStatus.UNMATCHED, unmatched_id=pending)

        correspondents = self._correspondents(email, user["email"])
        attachment_names = [attachment.filename for attachment in email.attachments]
        occurred_at = email.date or now
        subject = email.subject[:500]
        mandate_id = await self._deal(db, user, subject, now)
        contact_ids = (
            list(
                (
                    await db.execute(
                        select(Contact.id).where(func.lower(Contact.email).in_(correspondents)).order_by(Contact.id)
                    )
                ).scalars()
            )
            if correspondents
            else []
        )
        if not contact_ids:
            unmatched = UnmatchedEmail(
                user_id=user["id"],
                message_id=message_id,
                sender=addresses([email.sender])[0],
                subject=subject,
                body=email.text[:NOTE_LIMIT],
                correspondents=correspondents,
                attachment_names=attachment_names,
                occurred_at=occurred_at,
                received_at=now,
                mandate_id=mandate_id,
            )
            db.add(unmatched)
            await db.flush()
            self.audit.record(
                db,
                context,
                "unmatched_email.created",
                record_type="unmatched_email",
                record_id=unmatched.id,
                new_values={"subject": subject, "correspondents": correspondents},
            )
            await db.commit()
            return InboundResult(status=InboundStatus.UNMATCHED, unmatched_id=unmatched.id)

        links = [RecordRef(record_type=RecordType.CONTACT, record_id=cid) for cid in contact_ids]
        if mandate_id is not None:
            links.append(RecordRef(record_type=RecordType.MANDATE, record_id=mandate_id))
        activity_id = await self._log(
            db, user, subject, email.text, correspondents, attachment_names, occurred_at, links, now, context
        )
        db.add(
            LoggedEmail(
                user_id=user["id"],
                activity_id=activity_id,
                message_id=message_id,
                sender=addresses([email.sender])[0],
                subject=subject,
                attachment_names=attachment_names,
                received_at=now,
            )
        )
        await db.commit()
        return InboundResult(status=InboundStatus.LOGGED, activity_id=activity_id)

    async def _log(
        self,
        db: AsyncSession,
        user: dict[str, Any],
        subject: str,
        body: str,
        correspondents: list[str],
        attachment_names: list[str],
        occurred_at: datetime,
        links: list[RecordRef],
        now: datetime,
        context: AuditContext,
    ) -> int:
        values = ActivityCreate(
            type=ActivityType.EMAIL,
            occurred_at=occurred_at,
            participants=[address[:200] for address in correspondents[:50]],
            note=note_for(subject, body, attachment_names),
            links=links[:20],
        )
        return int((await self.activities.create(db, user, values, now, context))["id"])

    async def unmatched(self, db: AsyncSession, user: dict[str, Any]) -> list[UnmatchedEmail]:
        query = (
            select(UnmatchedEmail)
            .where(UnmatchedEmail.user_id == user["id"])
            .order_by(UnmatchedEmail.received_at.desc(), UnmatchedEmail.id.desc())
        )
        return list((await db.execute(query)).scalars())

    async def _own(self, db: AsyncSession, user: dict[str, Any], unmatched_id: int) -> UnmatchedEmail:
        item = await db.get(UnmatchedEmail, unmatched_id)
        if item is None or item.user_id != user["id"]:
            raise UnmatchedEmailNotFoundError(f"Unmatched email {unmatched_id} not found")
        return item

    async def link(
        self,
        db: AsyncSession,
        user: dict[str, Any],
        unmatched_id: int,
        values: UnmatchedLink,
        now: datetime,
        context: AuditContext,
    ) -> dict[str, Any]:
        item = await self._own(db, user, unmatched_id)
        links = list(values.links)
        if item.mandate_id is not None:
            links.append(RecordRef(record_type=RecordType.MANDATE, record_id=item.mandate_id))
        activity_id = await self._log(
            db, user, item.subject, item.body, item.correspondents, item.attachment_names, item.occurred_at, links, now, context
        )
        db.add(
            LoggedEmail(
                user_id=user["id"],
                activity_id=activity_id,
                message_id=item.message_id,
                sender=item.sender,
                subject=item.subject,
                attachment_names=item.attachment_names,
                received_at=item.received_at,
            )
        )
        self.audit.record(
            db,
            context,
            "unmatched_email.linked",
            record_type="unmatched_email",
            record_id=item.id,
            new_values={"activity_id": activity_id},
        )
        await db.delete(item)
        await db.commit()
        return {"id": activity_id}

    async def discard(self, db: AsyncSession, user: dict[str, Any], unmatched_id: int, context: AuditContext) -> None:
        item = await self._own(db, user, unmatched_id)
        self.audit.record(db, context, "unmatched_email.discarded", record_type="unmatched_email", record_id=item.id)
        await db.delete(item)
        await db.commit()


INTERACTION_TYPES = (ActivityType.EMAIL.value, ActivityType.MEETING.value)


async def interactions(db: AsyncSession, user: dict[str, Any], contact_id: int, now: datetime) -> list[dict[str, Any]]:
    """Per colleague: emails and meetings with this contact. Activities on deals the reader cannot see do not count."""
    if await db.get(Contact, contact_id) is None:
        raise ContactNotFoundError(f"Contact {contact_id} not found")
    visible = set(await DealPolicy(now).visible_mandate_ids(db, user))
    on_contact = select(ActivityLink.activity_id).where(
        ActivityLink.record_type == RecordType.CONTACT.value, ActivityLink.record_id == contact_id
    )
    hidden = select(ActivityLink.activity_id).where(
        ActivityLink.record_type == RecordType.MANDATE.value, ActivityLink.record_id.not_in(visible or {-1})
    )
    query = (
        select(Activity.author_id, User.name, func.count(Activity.id), func.max(Activity.occurred_at))
        .join(User, User.id == Activity.author_id)
        .where(
            Activity.id.in_(on_contact),
            Activity.id.not_in(hidden),
            Activity.deleted_at.is_(None),
            Activity.type.in_(INTERACTION_TYPES),
        )
        .group_by(Activity.author_id, User.name)
        .order_by(func.max(Activity.occurred_at).desc(), Activity.author_id)
    )
    return [
        {"user_id": uid, "name": name, "count": count, "last_interaction_at": last}
        for uid, name, count, last in (await db.execute(query)).tuples()
    ]
