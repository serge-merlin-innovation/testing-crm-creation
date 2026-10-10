from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.user.crud import crud_users
from ...modules.user.schemas import UserRead
from ..database.session import async_session
from .setup import auth


async def get_current_principal(
    principal: Annotated[Principal, Depends(auth.current_user())],
) -> Principal:
    return principal


async def get_optional_principal(
    principal: Annotated[Principal | None, Depends(auth.current_user(optional=True))],
) -> Principal | None:
    return principal


async def _load_user(db: AsyncSession, user_id: Any) -> dict[str, Any] | None:
    # Read on every request, never cached on the session, so a role or permission change applies
    # at the caller's next request.
    return await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)


async def get_current_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any]:
    if principal is None:
        raise UnauthorizedException("Not authenticated")

    user = await _load_user(db, principal.user_id)
    if user is None:
        raise UnauthorizedException("Not authenticated")
    return user


async def get_optional_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any] | None:
    if principal is None:
        return None
    return await _load_user(db, principal.user_id)
