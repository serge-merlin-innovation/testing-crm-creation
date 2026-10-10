from typing import Annotated, Any

from crudauth.exceptions import ForbiddenException
from fastapi import Depends

from ...infrastructure.auth.dependencies import get_current_user
from .permissions import Permission


def has_permission(user: dict[str, Any], permission: Permission) -> bool:
    return permission.value in (user.get("permissions") or [])


def require_permission(permission: Permission) -> Any:
    """Server-side gate for one permission, read fresh from the database on every request."""

    async def dependency(current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
        if not has_permission(current_user, permission):
            raise ForbiddenException("You don't have permission for this action.")
        return current_user

    dependency.__name__ = f"require_{permission.name.lower()}"
    return Depends(dependency)
