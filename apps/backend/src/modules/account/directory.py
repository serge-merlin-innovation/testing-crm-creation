import csv
import io
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.spreadsheet import safe_dict
from ..role.models import Role
from ..security.models import UserSecurity
from ..user.models import User
from .service import INVITATION_TTL

DORMANT_AFTER = timedelta(days=90)
EXPORT_COLUMNS = ["first_name", "last_name", "email", "title", "role", "status", "last_login_at", "dormant"]


def _row(user: User, role_name: str | None, last_login: datetime | None, now: datetime) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "title": user.title,
        "role_id": user.role_id,
        "role_name": role_name,
        "status": "inactive" if user.is_deleted else user.status,
        "invited_at": user.invited_at,
        "last_login_at": last_login,
        "dormant": user.status == "active" and last_login is not None and now - last_login > DORMANT_AFTER,
        "can_resend_invitation": user.status == "invited"
        and (user.invited_at is None or now - user.invited_at >= INVITATION_TTL),
    }


async def list_users(
    db: AsyncSession, now: datetime, role_id: int | None, status: str | None, offset: int = 0, limit: int | None = None
) -> tuple[list[dict[str, Any]], int]:
    query = (
        select(User, Role.name, UserSecurity.last_login_at)
        .outerjoin(Role, Role.id == User.role_id)
        .outerjoin(UserSecurity, UserSecurity.user_id == User.id)
    )
    if status == "inactive":
        query = query.where(User.is_deleted.is_(True), User.role_id.is_not(None))
    else:
        query = query.where(User.is_deleted.is_(False))
    if role_id is not None:
        query = query.where(User.role_id == role_id)
    if status in ("invited", "active"):
        query = query.where(User.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    query = query.order_by(User.id).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    rows = [_row(user, role, last, now) for user, role, last in (await db.execute(query)).all()]
    return rows, total


def to_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            safe_dict(
                {
                    **row,
                    "role": row["role_name"],
                    "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else "",
                    "dormant": "yes" if row["dormant"] else "no",
                }
            )
        )
    return buffer.getvalue()
