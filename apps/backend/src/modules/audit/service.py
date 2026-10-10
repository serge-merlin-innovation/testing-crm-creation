from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.client_ip import client_ip
from ...infrastructure.clock import Clock
from .models import RETENTION_YEARS, AuditEntry


@dataclass(frozen=True)
class AuditContext:
    """Who is acting and from where. Built once per request by `AuditContextDep`."""

    user_id: int | None
    ip_address: str | None
    user_agent: str | None
    clock: Clock

    @classmethod
    def from_request(cls, request: Request, user_id: int | None, clock: Clock) -> "AuditContext":
        return cls(
            user_id=user_id,
            ip_address=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
            clock=clock,
        )


def retention_end(at: datetime) -> datetime:
    try:
        return at.replace(year=at.year + RETENTION_YEARS)
    except ValueError:
        return at.replace(year=at.year + RETENTION_YEARS, day=28)


class AuditService:
    def record(
        self,
        db: AsyncSession,
        context: AuditContext,
        action: str,
        *,
        record_type: str | None = None,
        record_id: Any = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        user_id: int | None = None,
    ) -> AuditEntry:
        """Adds the entry to the caller's transaction; it commits or rolls back with the change."""
        now = context.clock.now()
        entry = AuditEntry(
            action=action,
            created_at=now,
            retain_until=retention_end(now),
            user_id=user_id if user_id is not None else context.user_id,
            record_type=record_type,
            record_id=None if record_id is None else str(record_id),
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            old_values=old_values,
            new_values=new_values,
        )
        db.add(entry)
        return entry

    async def search(
        self,
        db: AsyncSession,
        *,
        user_id: int | None = None,
        record_type: str | None = None,
        record_id: str | None = None,
        action: str | None = None,
        scope: Any = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        conditions = []
        if user_id is not None:
            conditions.append(AuditEntry.user_id == user_id)
        if record_type is not None:
            conditions.append(AuditEntry.record_type == record_type)
        if record_id is not None:
            conditions.append(AuditEntry.record_id == record_id)
        if action is not None:
            conditions.append(AuditEntry.action == action)
        if scope is not None:
            conditions.append(scope)

        total = (await db.execute(select(func.count()).select_from(AuditEntry).where(*conditions))).scalar_one()
        rows = (
            await db.execute(
                select(AuditEntry)
                .where(*conditions)
                .order_by(AuditEntry.created_at.desc(), AuditEntry.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
        return {"data": list(rows), "total_count": total}
