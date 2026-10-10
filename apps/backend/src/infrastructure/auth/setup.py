from crudauth import CookieConfig, CRUDAuth, IdentityConfig, SessionTransport
from crudauth.ratelimit import MemoryRateLimiterBackend

from ...modules.user.models import User
from ..config.settings import settings
from ..database.session import async_session

auth = CRUDAuth(
    session=async_session,
    user_model=User,
    SECRET_KEY=settings.SECRET_KEY,
    identity=IdentityConfig(login=["email"], recovery="email"),
    cookies=CookieConfig(secure=settings.SESSION_SECURE_COOKIES),
    transports=[
        SessionTransport(
            backend="memory",
            csrf=settings.CSRF_ENABLED,
            max_sessions_per_user=settings.MAX_SESSIONS_PER_USER,
            session_timeout_minutes=settings.SESSION_TIMEOUT_MINUTES,
            cleanup_interval_minutes=settings.SESSION_CLEANUP_INTERVAL_MINUTES,
        )
    ],
    rate_limiter=MemoryRateLimiterBackend(),
    trusted_proxy_hops=settings.TRUSTED_PROXY_HOPS,
    warn_on_memory_backend=False,
)
