from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.user.crud import crud_users
from ...modules.user.schemas import UserRead
from ..database.session import async_session
from .setup import auth


async def get_current_principal(
    principal: Annotated[Principal, Depends(auth.current_user())],
) -> Principal:
    return principal


BearerResolver = Callable[[Request, AsyncSession, str], Awaitable[Principal]]
_bearer_resolver: BearerResolver | None = None


def set_bearer_resolver(resolver: BearerResolver | None) -> None:
    """Registered at startup by the API-access module, which owns API tokens (NFR-05)."""
    global _bearer_resolver
    _bearer_resolver = resolver


async def get_optional_principal(
    request: Request,
    db: Annotated[AsyncSession, Depends(async_session)],
    session_principal: Annotated[Principal | None, Depends(auth.current_user(optional=True))],
) -> Principal | None:
    scheme, _, credential = (request.headers.get("authorization") or "").partition(" ")
    if scheme.lower() == "basic":
        raise UnauthorizedException("Basic authentication is not supported. Use an API token or OAuth 2.0 client credentials.")
    if scheme.lower() == "bearer":
        if _bearer_resolver is None or not credential.strip():
            raise UnauthorizedException("Not authenticated")
        return await _bearer_resolver(request, db, credential.strip())
    return session_principal


async def _load_user(db: AsyncSession, user_id: Any) -> dict[str, Any] | None:
    # Read on every request, never cached on the session, so a role or permission change applies
    # at the caller's next request.
    return await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)


def _remember_language(request: Request, user: dict[str, Any] | None) -> None:
    # The error localizer (infrastructure/i18n/middleware.py) answers in this language (NFR-04).
    if user is not None:
        request.state.language = user.get("language")


async def get_current_user(
    request: Request,
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any]:
    if principal is None:
        raise UnauthorizedException("Not authenticated")

    user = await _load_user(db, principal.user_id)
    if user is None:
        raise UnauthorizedException("Not authenticated")
    _remember_language(request, user)
    return user


async def get_optional_user(
    request: Request,
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any] | None:
    if principal is None:
        return None
    user = await _load_user(db, principal.user_id)
    _remember_language(request, user)
    return user
