from datetime import datetime, timedelta
from typing import Any

from crudauth.transports.session.schemas import SessionData
from crudauth.transports.session.useragent import parse_user_agent
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.clocked_sessions import (
    ABSOLUTE_EXPIRES_KEY,
    IDLE_SECONDS_KEY,
    MOBILE_KEY,
    ClockedSessionManager,
)
from ..audit.service import AuditContext, AuditService
from .models import SessionPolicy
from .schemas import SessionPolicyValues, SessionStatus

WARNING_SECONDS = 120


class SessionService:
    def __init__(self, manager: ClockedSessionManager) -> None:
        self.manager = manager
        self.audit = AuditService()

    async def policy(self, db: AsyncSession) -> SessionPolicy:
        policy = await db.get(SessionPolicy, 1)
        if policy is None:
            policy = SessionPolicy(id=1)
            db.add(policy)
            await db.flush()
        return policy

    async def set_policy(self, db: AsyncSession, values: SessionPolicyValues, context: AuditContext) -> SessionPolicy:
        policy = await self.policy(db)
        old = SessionPolicyValues.model_validate(policy, from_attributes=True).model_dump()
        for field, value in values.model_dump().items():
            setattr(policy, field, value)
        self.audit.record(
            db,
            context,
            "session.policy_changed",
            record_type="session_policy",
            record_id=1,
            old_values=old,
            new_values=values.model_dump(),
        )
        await db.commit()
        return policy

    async def metadata_for_new_session(self, db: AsyncSession, user_agent: str, now: datetime) -> dict[str, Any]:
        policy = await self.policy(db)
        mobile = parse_user_agent(user_agent).is_mobile
        idle = policy.mobile_idle_minutes if mobile else policy.desktop_idle_minutes
        return {
            IDLE_SECONDS_KEY: idle * 60,
            ABSOLUTE_EXPIRES_KEY: (now + timedelta(hours=policy.absolute_hours)).isoformat(),
            MOBILE_KEY: mobile,
        }

    async def status(self, db: AsyncSession, session: SessionData) -> SessionStatus:
        policy = await self.policy(db)
        return SessionStatus(
            idle_expires_at=self.manager.idle_expires_at(session),
            absolute_expires_at=self.manager.absolute_expires_at(session),
            warning_seconds=WARNING_SECONDS,
            mobile=bool(session.metadata.get(MOBILE_KEY)),
            mobile_read_only=policy.mobile_read_only,
        )

    async def revoke_all(self, db: AsyncSession, user_id: int, context: AuditContext) -> int:
        revoked = await self.manager.revoke_all(user_id)
        self.audit.record(
            db, context, "logout.everywhere", record_type="user", record_id=user_id, new_values={"revoked": revoked}
        )
        await db.commit()
        return revoked
