from typing import Annotated, Any

from fastapi import APIRouter

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import UserServiceDep
from .schemas import UserRead, UserRoleUpdate, UserUpdate

router = APIRouter(tags=["Users"])

UserManagerDep = Annotated[dict[str, Any], require_permission(Permission.USERS_MANAGE)]


@router.get(
    "/me",
    response_model=UserRead,
    summary="Current user, with the role's permissions so the UI can hide controls",
    responses={401: {"description": "Not authenticated"}},
)
async def get_current_user_profile(current_user: CurrentUserDep) -> dict[str, Any]:
    return current_user


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get a user",
    responses={403: {"description": "Not yourself and no users.manage"}, 404: {"description": "User not found"}},
)
async def get_user(
    user_id: int,
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    user_service: UserServiceDep,
) -> dict[str, Any]:
    user_service.verify_self_or_manager(current_user, user_id)
    return await user_service.get_by_id(user_id, db)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update a user's profile",
    responses={403: {"description": "Not yourself and no users.manage"}, 409: {"description": "Email already exists"}},
)
async def update_user(
    user_id: int,
    values: UserUpdate,
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    user_service: UserServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    user_service.verify_self_or_manager(current_user, user_id)
    return await user_service.update(user_id, values, db, context)


@router.delete(
    "/{user_id}/personal-data",
    summary="Anonymise a user's personal data (Admin)",
    responses={403: {"description": "Requires users.manage, or this is the last Admin"}},
)
async def anonymize_user(
    user_id: int,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
) -> dict[str, str]:
    await user_service.anonymize_user(user_id, db, context)
    return {"message": "User data anonymised"}


@router.patch(
    "/{user_id}/role",
    response_model=UserRead,
    summary="Change a user's role (Admin)",
    description="Replaces the user's single role. Applies at the user's next request and is audited.",
    responses={403: {"description": "Requires users.manage, or this demotes the last Admin"}},
)
async def change_user_role(
    user_id: int,
    values: UserRoleUpdate,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
) -> dict[str, Any]:
    return await user_service.change_role(user_id, values, db, context)


@router.post(
    "/{user_id}/roles",
    response_model=UserRead,
    summary="Grant a role to a user who has none (Admin)",
    description="One role per user in v1: granting a role to a user who already holds one returns 409.",
    responses={409: {"description": "The user already holds a role"}},
)
async def add_user_role(
    user_id: int,
    values: UserRoleUpdate,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
) -> dict[str, Any]:
    return await user_service.add_role(user_id, values, db, context)
