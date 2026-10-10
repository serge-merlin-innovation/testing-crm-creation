from typing import Annotated, Any

from fastapi import APIRouter, Query

from ...infrastructure.auth.http_exceptions import NotFoundException
from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import OffboardingServiceDep
from .schemas import DeactivateRequest, OffboardingConfirmation, OffboardingPreview, Reactivated

router = APIRouter(tags=["Users"])

UserManagerDep = Annotated[dict[str, Any], require_permission(Permission.USERS_MANAGE)]


@router.get(
    "/{user_id}/offboarding",
    response_model=OffboardingPreview,
    summary="What a deactivation would hand over (Admin)",
)
async def preview_offboarding(
    user_id: int, db: AsyncSessionDep, service: OffboardingServiceDep, _: UserManagerDep
) -> OffboardingPreview:
    return await service.preview(db, user_id)


@router.post(
    "/{user_id}/deactivate",
    response_model=OffboardingConfirmation,
    summary="Deactivate a leaver and hand over their records (Admin)",
    description="Ends every session, revokes API tokens and clients, removes deal team memberships and "
    "moves owned contacts, open tasks and led deals to `new_owner_id`, which is required when there is anything to move.",
    responses={422: {"description": "A new owner is required, or is not allowed"}, 403: {"description": "Last Admin"}},
)
async def deactivate_user(
    user_id: int,
    values: DeactivateRequest,
    db: AsyncSessionDep,
    service: OffboardingServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
) -> OffboardingConfirmation:
    return await service.deactivate(db, user_id, values.new_owner_id, context)


@router.delete(
    "/{user_id}",
    response_model=OffboardingConfirmation,
    summary="Deactivate a user (Admin)",
    description="Same as POST /users/{user_id}/deactivate, with the new owner as a query parameter.",
    responses={403: {"description": "Requires users.manage, or this is the last Admin"}},
)
async def delete_user(
    user_id: int,
    db: AsyncSessionDep,
    service: OffboardingServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
    new_owner_id: Annotated[int | None, Query()] = None,
) -> OffboardingConfirmation:
    return await service.deactivate(db, user_id, new_owner_id, context)


@router.get(
    "/{user_id}/offboarding/confirmation",
    response_model=OffboardingConfirmation,
    summary="The confirmation of the last deactivation (Admin)",
)
async def offboarding_confirmation(
    user_id: int, db: AsyncSessionDep, service: OffboardingServiceDep, _: UserManagerDep
) -> OffboardingConfirmation:
    confirmation = await service.last_confirmation(db, user_id)
    if confirmation is None:
        raise NotFoundException("This user was never deactivated.")
    return confirmation


@router.post(
    "/{user_id}/reactivate",
    response_model=Reactivated,
    summary="Reactivate a user: role back, no deal team memberships (Admin)",
)
async def reactivate_user(
    user_id: int, db: AsyncSessionDep, service: OffboardingServiceDep, context: AuditContextDep, _: UserManagerDep
) -> Reactivated:
    return await service.reactivate(db, user_id, context)
