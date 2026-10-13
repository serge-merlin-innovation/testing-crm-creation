from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.dependencies import get_current_user, get_optional_user
from .database.session import async_session

AsyncSessionDep = Annotated[AsyncSession, Depends(async_session)]

CurrentUserDep = Annotated[dict[str, Any], Depends(get_current_user)]
OptionalUserDep = Annotated[dict[str, Any] | None, Depends(get_optional_user)]
