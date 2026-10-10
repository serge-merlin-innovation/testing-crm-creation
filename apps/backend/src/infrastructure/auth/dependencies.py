from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...modules.user.crud import crud_users
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


async def get_current_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any]:
    credentials_exception = UnauthorizedException("Not authenticated")

    if principal is None:
        raise credentials_exception

    user = await crud_users.get(db=db, id=principal.user_id, is_deleted=False)

    if user is None:
        raise credentials_exception

    return user


async def get_optional_user(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: Annotated[AsyncSession, Depends(async_session)],
) -> dict[str, Any] | None:
    if principal is None:
        return None

    return await crud_users.get(db=db, id=principal.user_id, is_deleted=False)


async def get_current_superuser(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    if not current_user.get("is_superuser", False):
        raise ForbiddenException("Insufficient privileges")

    return current_user
