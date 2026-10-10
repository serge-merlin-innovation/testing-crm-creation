from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.dependencies import get_current_user
from ...infrastructure.auth.http_exceptions import HTTPException
from ...infrastructure.clock import Clock, get_clock
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
