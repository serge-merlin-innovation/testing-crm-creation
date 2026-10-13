import csv
import io
import secrets
from datetime import datetime, timedelta
from typing import Any

from crudauth import get_password_hash, verify_password
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.setup import auth as crud_auth
from ...infrastructure.config.settings import settings
from ...infrastructure.email import EmailMessage, get_email_sender
from ...infrastructure.i18n.localize import localize
from ..audit.service import AuditContext, AuditService
from ..common.exceptions import DomainError, RoleNotFoundError, UserExistsError, UserNotFoundError, ValidationError
from ..common.hashing import sha256_hex
from ..role.models import Role
from ..security.models import TrustedDevice
from ..user.models import User
from ..user.schemas import UserCreate
from .models import AccountToken, PasswordResetRequest
from .policy import set_password

INVITATION_TTL = timedelta(hours=72)
RESET_TTL = timedelta(minutes=30)
RESET_LIMIT = 3
RESET_WINDOW = timedelta(hours=1)
INVITE = "invite"
RESET = "reset"


class LinkRefusedError(DomainError):
    pass


class TooManyResetRequestsError(DomainError):
    pass


async def _send(to: str, subject: str, body: str, language: str | None = None) -> None:
    await get_email_sender().send(EmailMessage(to=to, subject=localize(subject, language), body=localize(body, language)))


class AccountService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def _issue(self, db: AsyncSession, user_id: int, kind: str, ttl: timedelta, now: datetime) -> str:
        await db.execute(
            update(AccountToken)
            .where(AccountToken.user_id == user_id, AccountToken.kind == kind, AccountToken.used_at.is_(None))
            .values(used_at=now)
        )
        token = secrets.token_urlsafe(32)
        db.add(AccountToken(user_id=user_id, kind=kind, token_hash=sha256_hex(token), created_at=now, expires_at=now + ttl))
        return token

    async def _redeem(self, db: AsyncSession, token: str, kind: str, now: datetime) -> tuple[AccountToken, User]:
        found = (
            await db.execute(
                select(AccountToken).where(AccountToken.token_hash == sha256_hex(token), AccountToken.kind == kind)
            )
        ).scalar_one_or_none()
        user = await db.get(User, found.user_id) if found else None
        if found is None or user is None or user.is_deleted or found.used_at is not None or found.expires_at <= now:
            raise LinkRefusedError(kind)
        return found, user

    async def _role_name(self, db: AsyncSession, role_id: int) -> str:
        name = (await db.execute(select(Role.name).where(Role.id == role_id, Role.is_deleted.is_(False)))).scalar_one_or_none()
        if name is None:
            raise RoleNotFoundError(f"Role with ID {role_id} not found")
        return name

    async def invite(self, db: AsyncSession, values: UserCreate, context: AuditContext) -> int:
        now = context.clock.now()
        email = values.email.strip().lower()
        if (await db.execute(select(User.id).where(func.lower(User.email) == email))).first():
            raise UserExistsError("Email already registered")
        role = await self._role_name(db, values.role_id)
        user = User(
            name=f"{values.first_name} {values.last_name}"[:100],
            email=email,
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),
            role_id=values.role_id,
            first_name=values.first_name,
            last_name=values.last_name,
            title=values.title,
            status="invited",
            invited_at=now,
        )
        db.add(user)
        await db.flush()
        token = await self._issue(db, user.id, INVITE, INVITATION_TTL, now)
        self.audit.record(
            db,
            context,
            "user.created",
            record_type="user",
            record_id=user.id,
            new_values={"name": user.name, "email": email, "role": role, "title": values.title, "status": "invited"},
        )
        await db.commit()
        await self._send_invitation(user, token)
        await _send(
            email,
            "Welcome to the CRM",
            f"Hello {values.first_name},\n\nAn account was created for you in the CRM ({settings.APP_URL}) "
            f"with the role {role}.\nUse the invitation email to set your password and two-factor authentication.",
        )
        return user.id

    async def _send_invitation(self, user: User, token: str) -> None:
        await _send(
            user.email,
            "You are invited to the CRM",
            f"Set your password and two-factor authentication within 72 hours:\n"
            f"{settings.APP_URL}/accept-invitation?token={token}\n\n"
            "The link works once. If it has expired, ask your administrator to resend it.",
            user.language,
        )

    async def resend_invitation(self, db: AsyncSession, user_id: int, context: AuditContext) -> None:
        user = await db.get(User, user_id)
        if user is None or user.is_deleted:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        if user.status != "invited":
            raise ValidationError("This user has already accepted the invitation.")
        now = context.clock.now()
        token = await self._issue(db, user.id, INVITE, INVITATION_TTL, now)
        user.invited_at = now
        self.audit.record(db, context, "user.invitation_resent", record_type="user", record_id=user.id)
        await db.commit()
        await self._send_invitation(user, token)

    async def import_csv(self, db: AsyncSession, content: str, context: AuditContext) -> list[dict[str, Any]]:
        roles = {
            name: role_id for role_id, name in (await db.execute(select(Role.id, Role.name).where(Role.is_deleted.is_(False))))
        }
        results: list[dict[str, Any]] = []
        for line, row in enumerate(csv.DictReader(io.StringIO(content.lstrip("\ufeff"))), start=2):
            role_id = _match_role(roles, (row.get("role") or "").strip())
            result: dict[str, Any] = {"line": line, "email": (row.get("email") or "").strip()}
            try:
                if role_id is None:
                    raise ValidationError("Unknown role.", field="role")
                values = UserCreate(
                    first_name=(row.get("first_name") or "").strip(),
                    last_name=(row.get("last_name") or "").strip(),
                    email=result["email"],
                    title=(row.get("title") or "").strip() or None,
                    role_id=role_id,
                )
                result["id"] = await self.invite(db, values, context)
                result["status"] = "created"
            except PydanticValidationError as exc:
                error = exc.errors()[0]
                result |= {"status": "error", "field": str(error["loc"][0]), "message": error["msg"]}
            except ValidationError as exc:
                result |= {"status": "error", "field": exc.field, "message": str(exc)}
            except UserExistsError:
                await db.rollback()
                result |= {"status": "error", "field": "email", "message": "A user with this email already exists."}
            results.append(result)
        return results

    async def invitation(self, db: AsyncSession, token: str, now: datetime) -> User:
        return (await self._redeem(db, token, INVITE, now))[1]

    async def accept_invitation(self, db: AsyncSession, token: str, password: str, context: AuditContext) -> User:
        now = context.clock.now()
        link, user = await self._redeem(db, token, INVITE, now)
        await set_password(db, user, password, now)
        link.used_at = now
        user.status = "active"
        user.email_verified = True
        self.audit.record(db, context, "user.invitation_accepted", record_type="user", record_id=user.id, user_id=user.id)
        return user

    async def request_reset(self, db: AsyncSession, email: str, context: AuditContext) -> None:
        now = context.clock.now()
        email = email.strip().lower()
        recent = (
            await db.execute(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.email == email, PasswordResetRequest.at > now - RESET_WINDOW)
            )
        ).scalar_one()
        if recent >= RESET_LIMIT:
            raise TooManyResetRequestsError(email)
        db.add(PasswordResetRequest(email=email, at=now))
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email, User.is_deleted.is_(False)))
        ).scalar_one_or_none()
        token = None
        if user is not None and user.status == "active":
            token = await self._issue(db, user.id, RESET, RESET_TTL, now)
            self.audit.record(db, context, "user.password_reset_requested", record_type="user", record_id=user.id)
        await db.commit()
        if user is not None and token is not None:
            await _send(
                user.email,
                "Reset your CRM password",
                f"Choose a new password within 30 minutes:\n{settings.APP_URL}/reset-password?token={token}\n\n"
                "The link works once. If you did not ask for it, ignore this email.",
                user.language,
            )

    async def _after_password_change(
        self, db: AsyncSession, user: User, context: AuditContext, action: str, keep_session: str | None = None
    ) -> None:
        await db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user.id))
        self.audit.record(db, context, action, record_type="user", record_id=user.id, user_id=user.id)
        await db.commit()
        await crud_auth.sessions.revoke_all(user.id, exclude=keep_session)
        await _send(
            user.email,
            "Your CRM password was changed",
            f"The password of {user.email} was changed. If this was not you, contact your administrator now.",
            user.language,
        )

    async def reset_password(self, db: AsyncSession, token: str, password: str, context: AuditContext) -> None:
        now = context.clock.now()
        link, user = await self._redeem(db, token, RESET, now)
        await set_password(db, user, password, now)
        link.used_at = now
        await self._after_password_change(db, user, context, "user.password_reset")

    async def change_password(
        self, db: AsyncSession, user_id: int, current: str, new: str, context: AuditContext, session_id: str | None
    ) -> None:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID {user_id} not found")
        if not verify_password(current, user.hashed_password):
            raise ValidationError("Your current password is not correct.", field="current_password")
        await set_password(db, user, new, context.clock.now(), field="new_password")
        await self._after_password_change(db, user, context, "user.password_changed", keep_session=session_id)


def _match_role(roles: dict[str, int], wanted: str) -> int | None:
    """A CSV may name a role in full ("Analyst / Associate") or by one of its parts ("Analyst")."""
    lowered = wanted.lower()
    for name, role_id in roles.items():
        if lowered and (lowered == name.lower() or lowered in (part.strip().lower() for part in name.split("/"))):
            return role_id
    return None
