import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta
from typing import Any

from crudauth.ratelimit.constants import LOCKOUT_NAMESPACE
from crudauth.utils import canonical_identifier
from sqlalchemy import String, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.setup import auth as crud_auth
from ...infrastructure.config.settings import settings
from ...infrastructure.email import EmailMessage, get_email_sender
from ...infrastructure.geoip import EU_COUNTRIES, get_geoip
from ...infrastructure.i18n.localize import localize
from ..audit.service import AuditContext, AuditService
from ..common.hashing import sha256_hex
from ..role.models import Role
from ..user.models import User
from .models import KnownLoginMarker, LoginFailure, RecoveryCode, SecurityPolicy, TrustedDevice, UserSecurity
from .totp import new_secret, provisioning_uri, verify_totp

MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
TRUST_DURATION = timedelta(days=30)
CHALLENGE_TTL = timedelta(minutes=5)
RECOVERY_CODE_COUNT = 10


RECOVERY_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
RECOVERY_CODE_LENGTH = 12


def _new_recovery_code() -> str:
    symbols = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
    return "-".join(symbols[index : index + 4] for index in range(0, RECOVERY_CODE_LENGTH, 4))


def _normalise_recovery_code(code: str) -> str:
    return "".join(character for character in code.upper() if character.isalnum())


def _recovery_hash(code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"recovery:{_normalise_recovery_code(code)}".encode(), hashlib.sha256
    ).hexdigest()


def _sign(payload: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_challenge(user_id: int, now: datetime) -> str:
    payload = f"{user_id}.{int((now + CHALLENGE_TTL).timestamp())}.{secrets.token_hex(8)}"
    return f"{payload}.{_sign(payload)}"


def read_challenge(token: str, now: datetime) -> int | None:
    payload, _, signature = token.rpartition(".")
    if not payload or not hmac.compare_digest(_sign(payload), signature):
        return None
    user_id, expires, _nonce = payload.split(".")
    if int(expires) < now.timestamp():
        return None
    return int(user_id)


def device_label(device_info: dict[str, Any]) -> str:
    return f"{device_info.get('browser', 'Unknown')} on {device_info.get('os', 'Unknown')}"[:200]


async def clear_throttle(email: str, ips: set[str]) -> None:
    """Drops crudauth's lockout for the account and the IPs it failed from, or an unlocked user meets a 429."""
    lockout = crud_auth.runtime.lockout
    if lockout is None:
        return
    for dimension, value in [("user", canonical_identifier(email)), *(("ip", ip) for ip in ips)]:
        for prefix in ("", "lock:", "rounds:"):
            await lockout.backend.delete(f"{LOCKOUT_NAMESPACE}:{prefix}{dimension}:{value}")


class SecurityService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def state(self, db: AsyncSession, user_id: int) -> UserSecurity:
        state = await db.get(UserSecurity, user_id)
        if state is None:
            state = UserSecurity(user_id=user_id)
            db.add(state)
            await db.flush()
        return state

    async def policy(self, db: AsyncSession) -> SecurityPolicy:
        policy = await db.get(SecurityPolicy, 1)
        if policy is None:
            policy = SecurityPolicy(id=1)
            db.add(policy)
            await db.flush()
        return policy

    async def admin_emails(self, db: AsyncSession) -> list[str]:
        statement = (
            select(User.email)
            .join(Role, Role.id == User.role_id)
            .where(
                User.is_deleted.is_(False), Role.is_deleted.is_(False), Role.permissions.cast(String).like('%"users.manage"%')
            )
        )
        return list((await db.execute(statement)).scalars().all())

    async def notify(self, db: AsyncSession, recipients: list[str], subject: str, body: str) -> None:
        sender = get_email_sender()
        addresses = list(dict.fromkeys(recipients))
        rows = await db.execute(select(User.email, User.language).where(User.email.in_(addresses)))
        languages: dict[str, str] = {email: language for email, language in rows.tuples()}
        for address in addresses:
            language = languages.get(address)
            await sender.send(EmailMessage(to=address, subject=localize(subject, language), body=localize(body, language)))

    def is_locked(self, state: UserSecurity, now: datetime) -> bool:
        return state.locked_until is not None and state.locked_until > now

    async def record_failure(self, db: AsyncSession, user: User, context: AuditContext, reason: str) -> bool:
        """Counts a failed or denied attempt. Returns True when this attempt locked the account."""
        now = context.clock.now()
        self.audit.record(
            db,
            context,
            "login.failed" if reason in ("password", "code") else "login.denied",
            record_type="user",
            record_id=user.id,
            user_id=user.id,
            new_values={"reason": reason},
        )
        db.add(LoginFailure(user_id=user.id, at=now, ip_address=context.ip_address))
        await db.flush()
        recent = (
            await db.execute(
                select(func.count())
                .select_from(LoginFailure)
                .where(LoginFailure.user_id == user.id, LoginFailure.at > now - FAILURE_WINDOW)
            )
        ).scalar_one()
        state = await self.state(db, user.id)
        if recent < MAX_FAILURES or self.is_locked(state, now):
            return False
        state.locked_until = now + LOCK_DURATION
        self.audit.record(db, context, "user.locked", record_type="user", record_id=user.id, user_id=user.id)
        await self.notify(
            db,
            await self.admin_emails(db),
            "Account locked",
            f"{user.email} was locked for 15 minutes after {MAX_FAILURES} failed or denied login attempts.",
        )
        return True

    async def unlock(self, db: AsyncSession, user_id: int, context: AuditContext) -> None:
        state = await self.state(db, user_id)
        old = state.locked_until
        state.locked_until = None
        ips = set((await db.execute(select(LoginFailure.ip_address).where(LoginFailure.user_id == user_id))).scalars())
        await db.execute(delete(LoginFailure).where(LoginFailure.user_id == user_id))
        email = (await db.execute(select(User.email).where(User.id == user_id))).scalar_one_or_none()
        if email:
            await clear_throttle(email, {ip for ip in ips if ip})
        self.audit.record(
            db,
            context,
            "user.unlocked",
            record_type="user",
            record_id=user_id,
            old_values={"locked_until": old.isoformat() if old else None},
        )
        await db.commit()

    async def reset_two_factor(self, db: AsyncSession, user_id: int, context: AuditContext) -> None:
        state = await self.state(db, user_id)
        state.totp_secret = None
        state.totp_enabled = False
        await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
        await db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user_id))
        self.audit.record(db, context, "user.2fa_reset", record_type="user", record_id=user_id)
        await db.commit()

    async def start_enrolment(self, db: AsyncSession, user: User) -> str:
        state = await self.state(db, user.id)
        if not state.totp_secret or state.totp_enabled:
            state.totp_secret = new_secret()
        return provisioning_uri(state.totp_secret, user.email)

    async def check_code(self, db: AsyncSession, state: UserSecurity, code: str, now: datetime) -> bool:
        if state.totp_secret and verify_totp(state.totp_secret, code, now):
            return True
        if not state.totp_enabled:
            return False
        recovery = (
            await db.execute(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == state.user_id,
                    RecoveryCode.code_hash == _recovery_hash(code),
                    RecoveryCode.used_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if recovery is None:
            return False
        recovery.used_at = now
        return True

    async def issue_recovery_codes(self, db: AsyncSession, user_id: int) -> list[str]:
        await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
        codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
        for code in codes:
            db.add(RecoveryCode(user_id=user_id, code_hash=_recovery_hash(code)))
        return codes

    async def trust_device(self, db: AsyncSession, user_id: int, now: datetime) -> str:
        token = secrets.token_urlsafe(32)
        db.add(TrustedDevice(user_id=user_id, token_hash=sha256_hex(token), expires_at=now + TRUST_DURATION))
        return token

    async def is_trusted_device(self, db: AsyncSession, user_id: int, token: str | None, now: datetime) -> bool:
        if not token or not (await self.policy(db)).trusted_devices_enabled:
            return False
        found = (
            await db.execute(
                select(TrustedDevice.id).where(
                    TrustedDevice.user_id == user_id,
                    TrustedDevice.token_hash == sha256_hex(token),
                    TrustedDevice.expires_at > now,
                )
            )
        ).scalar_one_or_none()
        return found is not None

    def is_travelling(self, state: UserSecurity, today: date) -> bool:
        return (
            state.travel_from is not None
            and state.travel_until is not None
            and state.travel_from <= today <= state.travel_until
        )

    async def complete_login(self, db: AsyncSession, user: User, context: AuditContext, device_info: dict[str, Any]) -> None:
        now = context.clock.now()
        state = await self.state(db, user.id)
        device = device_label(device_info)
        country = get_geoip().country(context.ip_address)
        state.last_login_at = now
        state.last_login_ip = context.ip_address
        state.last_login_device = device
        await db.execute(delete(LoginFailure).where(LoginFailure.user_id == user.id))

        known = {
            (marker.kind, marker.value)
            for marker in (await db.execute(select(KnownLoginMarker).where(KnownLoginMarker.user_id == user.id))).scalars()
        }
        seen = [("device", device)] + ([("country", country)] if country else [])
        new = [marker for marker in seen if marker not in known]
        for kind, value in new:
            db.add(KnownLoginMarker(user_id=user.id, kind=kind, value=value))

        travelling_abroad = self.is_travelling(state, now.date()) and country is not None and country not in EU_COUNTRIES
        if known and new and not travelling_abroad:
            details = ", ".join(f"new {kind}: {value}" for kind, value in new)
            body = f"A login to {user.email} succeeded from {context.ip_address or 'an unknown IP'} ({details})."
            await self.notify(db, [user.email, *await self.admin_emails(db)], "New login location or device", body)
            self.audit.record(db, context, "login.alert", record_type="user", record_id=user.id, new_values={"new": details})

        self.audit.record(db, context, "login", record_type="user", record_id=user.id, user_id=user.id)

    async def set_travel(
        self, db: AsyncSession, user_id: int, travel_from: date | None, travel_until: date | None, context: AuditContext
    ) -> UserSecurity:
        state = await self.state(db, user_id)
        old = {"travel_from": str(state.travel_from), "travel_until": str(state.travel_until)}
        state.travel_from, state.travel_until = travel_from, travel_until
        self.audit.record(
            db,
            context,
            "user.travel_changed",
            record_type="user",
            record_id=user_id,
            old_values=old,
            new_values={"travel_from": str(travel_from), "travel_until": str(travel_until)},
        )
        await db.commit()
        return state

    async def set_policy(self, db: AsyncSession, trusted_devices_enabled: bool, context: AuditContext) -> SecurityPolicy:
        policy = await self.policy(db)
        old = policy.trusted_devices_enabled
        policy.trusted_devices_enabled = trusted_devices_enabled
        if not trusted_devices_enabled:
            await db.execute(delete(TrustedDevice))
        self.audit.record(
            db,
            context,
            "security.policy_changed",
            record_type="security_policy",
            record_id=1,
            old_values={"trusted_devices_enabled": old},
            new_values={"trusted_devices_enabled": trusted_devices_enabled},
        )
        await db.commit()
        return policy
