from datetime import datetime, timedelta
from typing import Any

from crudauth import SessionTransport
from crudauth.transports.session.constants import CSRF_TOKEN_ID_META_KEY
from crudauth.transports.session.manager import SessionManager
from crudauth.transports.session.schemas import SessionData
from crudauth.transports.session.useragent import parse_user_agent
from crudauth.utils import get_client_ip
from fastapi import Request

from ..clock import Clock, SystemClock

_session_clock: Clock = SystemClock()


def get_session_clock() -> Clock:
    return _session_clock


def set_session_clock(clock: Clock) -> None:
    """Session expiry runs on its own clock so tests that move the app clock across days keep their sessions."""
    global _session_clock
    _session_clock = clock


IDLE_SECONDS_KEY = "idle_seconds"
ABSOLUTE_EXPIRES_KEY = "absolute_expires_at"
MOBILE_KEY = "mobile"


class ClockedSessionManager(SessionManager):
    """crudauth's manager with two additions: each session carries its own idle window and absolute
    expiry (stamped at creation, so a policy change only reaches new sessions), and time comes from
    the session clock so tests can move it."""

    def timeout_seconds_for(self, metadata: dict[str, Any] | None) -> int:
        if metadata and metadata.get(IDLE_SECONDS_KEY):
            return int(metadata[IDLE_SECONDS_KEY])
        return super().timeout_seconds_for(metadata)

    def idle_expires_at(self, session: SessionData) -> datetime:
        return session.last_activity + timedelta(seconds=self.timeout_seconds_for(session.metadata))

    @staticmethod
    def absolute_expires_at(session: SessionData) -> datetime | None:
        raw = session.metadata.get(ABSOLUTE_EXPIRES_KEY)
        return datetime.fromisoformat(raw) if raw else None

    def _is_idle_expired(self, session: SessionData, now: datetime) -> bool:
        absolute = self.absolute_expires_at(session)
        return now > self.idle_expires_at(session) or (absolute is not None and now >= absolute)

    async def create_session(
        self,
        request: Request,
        user_id: Any,
        metadata: dict[str, Any] | None = None,
        expiration_seconds: int | None = None,
    ) -> tuple[str, str]:
        now = get_session_clock().now()
        user_agent = request.headers.get("user-agent", "")
        await self._enforce_session_limit(user_id)
        session = SessionData(
            user_id=user_id,
            ip_address=get_client_ip(request, self.trusted_proxy_hops),
            user_agent=user_agent,
            device_info=parse_user_agent(user_agent).model_dump(),
            created_at=now,
            last_activity=now,
            metadata=metadata or {},
        )
        ttl = expiration_seconds if expiration_seconds is not None else self.timeout_seconds_for(session.metadata)
        csrf_token = await self._generate_csrf_token(user_id, session.session_id, ttl)
        if csrf_token:
            session.metadata[CSRF_TOKEN_ID_META_KEY] = csrf_token
        await self.storage.create(session, session_id=session.session_id, expiration=ttl)
        return session.session_id, csrf_token

    async def validate_session(self, session_id: str, update_activity: bool = True) -> SessionData | None:
        if not session_id:
            return None
        session = await self.storage.get(session_id, SessionData)
        if session is None:
            return None
        now = get_session_clock().now()
        if self._is_idle_expired(session, now):
            await self.terminate_session(session_id, reason="session_timeout", user_id=session.user_id)
            return None
        if update_activity:
            session.last_activity = now
            ttl = self.timeout_seconds_for(session.metadata)
            await self.storage.update(session_id, session, expiration=ttl)
            csrf_id = session.metadata.get(CSRF_TOKEN_ID_META_KEY)
            if csrf_id and self.csrf_storage is not None:
                await self.csrf_storage.extend(csrf_id, ttl)
        return session


class ClockedSessionTransport(SessionTransport):
    def bind(self, runtime: Any) -> None:
        super().bind(runtime)
        # The subclass adds behaviour only, no state, so re-typing the built manager is safe and
        # keeps every constructor argument crudauth passes in sync.
        assert self.manager is not None
        self.manager.__class__ = ClockedSessionManager

    @property
    def clocked(self) -> ClockedSessionManager:
        assert isinstance(self.manager, ClockedSessionManager)
        return self.manager
