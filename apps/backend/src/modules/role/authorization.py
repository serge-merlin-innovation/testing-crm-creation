from typing import Annotated, Any

from crudauth.exceptions import ForbiddenException
from fastapi import Depends

from ...infrastructure.auth.dependencies import get_current_user
from .permissions import Permission


def has_permission(user: dict[str, Any], permission: Permission) -> bool:
    return permission.value in (user.get("permissions") or [])


def is_compliance(user: dict[str, Any]) -> bool:
    return has_permission(user, Permission.CONFLICTS_REGISTER)


AGGREGATE_ONLY = frozenset({Permission.DASHBOARD_AGGREGATED.value, Permission.DASHBOARD_FIRM.value})


def has_record_access(user: dict[str, Any]) -> bool:
    """False for a role holding nothing beyond the aggregated dashboards (Read-only, ROLE-01 c3)."""
    return bool(set(user.get("permissions") or []) - AGGREGATE_ONLY)


async def _record_access(current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
    if not has_record_access(current_user):
        raise ForbiddenException("Your role sees the aggregated dashboards only.")
    return current_user


# Router-level guard for every deal, company, contact and record route.
RequireRecordAccess = Depends(_record_access)


def require_permission(permission: Permission) -> Any:
    """Server-side gate for one permission, read fresh from the database on every request."""

    async def dependency(current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
        if not has_permission(current_user, permission):
            raise ForbiddenException("You don't have permission for this action.")
        return current_user

    dependency.__name__ = f"require_{permission.name.lower()}"
    return Depends(dependency)
