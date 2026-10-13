from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.auth.dependencies import get_optional_principal
from ...infrastructure.clock import get_clock
from ...infrastructure.dependencies import CurrentUserDep
from .rate_limit import limiter
from .service import ApiAccessService

API_TRANSPORT = "api_token"


def get_api_access_service() -> ApiAccessService:
    return ApiAccessService()


async def resolve_bearer(request: Request, db: AsyncSession, secret: str) -> Principal:
    now = get_clock().now()
    identity = await ApiAccessService().resolve(db, secret, now)
    if identity is None:
        raise UnauthorizedException("Invalid or expired API token")
    retry_after = limiter.hit(identity.rate_key, now)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: 100 requests per minute per API client.",
            headers={"Retry-After": str(retry_after)},
        )
    return Principal(
        user_id=identity.user_id,
        transport=API_TRANSPORT,
        metadata={"api_token_id": identity.token_id, "kind": identity.kind},
    )


async def require_browser_session(
    principal: Annotated[Principal | None, Depends(get_optional_principal)], user: CurrentUserDep
) -> dict[str, Any]:
    """Credentials are managed from a signed-in CRM session, never by another API credential."""
    if principal is None:
        raise UnauthorizedException("Not authenticated")
    if principal.transport == API_TRANSPORT:
        raise ForbiddenException("API credentials are managed from the CRM, not over the API.")
    return user


ApiAccessServiceDep = Annotated[ApiAccessService, Depends(get_api_access_service)]
SessionUserDep = Annotated[dict[str, Any], Depends(require_browser_session)]
