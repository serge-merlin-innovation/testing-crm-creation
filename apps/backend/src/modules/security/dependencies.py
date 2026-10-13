from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.dependencies import get_current_user
from ...infrastructure.auth.http_exceptions import HTTPException
from ...infrastructure.clock import Clock, get_clock
from ...infrastructure.config.settings import settings
from ...infrastructure.database.session import async_session
from .service import SecurityService

STEP_UP_HEADER = "X-Step-Up-Code"


def get_security_service() -> SecurityService:
    return SecurityService()


SecurityServiceDep = Annotated[SecurityService, Depends(get_security_service)]


async def require_step_up(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(async_session)],
    clock: Annotated[Clock, Depends(get_clock)],
    service: SecurityServiceDep,
    code: Annotated[str | None, Header(alias=STEP_UP_HEADER)] = None,
) -> dict[str, Any]:
    """Asks the second factor again for a sensitive action: send the current code in X-Step-Up-Code."""
    state = await service.state(db, current_user["id"])
    if not code or not state.totp_enabled or not await service.check_code(db, state, code, clock.now()):
        raise HTTPException(
            status_code=401, detail="Enter your authentication code to confirm this action.", headers={"X-Step-Up": "required"}
        )
    return current_user


StepUpUserDep = Annotated[dict[str, Any], Depends(require_step_up)]


# Browsers send Sec-Fetch-Site on every request; "none" is a typed URL or a bookmark.
_SAME_SITE_FETCH = {"same-origin", "none"}


def require_same_origin(request: Request) -> None:
    """Login CSRF (AUTH-01 c5): a login POST has no session yet, so no CSRF token to check.
    Refuse it when the browser says another site sent it. Non-browser callers send neither header."""
    fetch_site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    if fetch_site is not None and fetch_site not in _SAME_SITE_FETCH:
        raise HTTPException(status_code=403, detail="Sign in from the CRM's own login page.")
    if origin is not None and origin.rstrip("/") != settings.APP_URL.rstrip("/"):
        raise HTTPException(status_code=403, detail="Sign in from the CRM's own login page.")


SameOriginDep = Depends(require_same_origin)
