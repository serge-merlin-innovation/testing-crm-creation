import re
from datetime import datetime

from crudauth import get_password_hash, verify_password
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.breach import get_breach_checker
from ..common.exceptions import ValidationError
from ..user.models import User
from .models import PasswordHistory, PasswordPolicy

MIN_LENGTH_FLOOR = 12
PERSONAL_PART_MIN = 3


async def current_policy(db: AsyncSession) -> PasswordPolicy:
    policy = await db.get(PasswordPolicy, 1)
    if policy is None:
        policy = PasswordPolicy(id=1)
        db.add(policy)
        await db.flush()
    return policy


def _personal_parts(user: User) -> set[str]:
    local = user.email.split("@")[0]
    words = [user.first_name or "", user.last_name or "", *re.split(r"[\s._+-]+", user.name or ""), local]
    words += re.split(r"[._+-]+", local)
    return {word.lower() for word in words if len(word) >= PERSONAL_PART_MIN} | {user.email.lower()}


async def check_password(db: AsyncSession, user: User, password: str, field: str = "password") -> None:
    """Applies the policy as it stands now; existing passwords are only checked again when next changed."""
    policy = await current_policy(db)
    if len(password) < policy.min_length:
        raise ValidationError(f"Use at least {policy.min_length} characters.", field=field)
    lowered = password.lower()
    if any(part in lowered for part in _personal_parts(user)):
        raise ValidationError("The password must not contain your name or email.", field=field)
    recent = (
        await db.execute(
            select(PasswordHistory.hashed_password)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.set_at.desc(), PasswordHistory.id.desc())
            .limit(policy.history_count)
        )
    ).scalars()
    if any(verify_password(password, hashed) for hashed in [user.hashed_password, *recent]):
        raise ValidationError("You used this password recently. Choose another.", field=field)
    if await get_breach_checker().is_breached(password):
        raise ValidationError("This password appears in a known data breach. Choose another.", field=field)


async def set_password(db: AsyncSession, user: User, password: str, at: datetime, field: str = "password") -> None:
    await check_password(db, user, password, field)
    user.hashed_password = get_password_hash(password)
    db.add(PasswordHistory(user_id=user.id, hashed_password=user.hashed_password, set_at=at))
