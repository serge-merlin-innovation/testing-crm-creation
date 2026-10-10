from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from fastapi import APIRouter, Depends, Request, Response

from ...infrastructure.auth.dependencies import get_current_principal
from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import SessionServiceDep
from .schemas import SessionPolicyValues, SessionsRevoked, SessionStatus

router = APIRouter(tags=["Sessions"])

SettingsManagerDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]
UserManagerDep = Annotated[dict[str, Any], require_permission(Permission.USERS_MANAGE)]


@router.get(
    "/auth/session",
    response_model=SessionStatus,
    summary="When the current session expires; reading it is not activity",
    responses={401: {"description": "No live session"}},
)
async def session_status(request: Request, db: AsyncSessionDep, service: SessionServiceDep) -> SessionStatus:
    manager = service.manager
    session_id = request.cookies.get(manager.session_cookie_name)
    session = await manager.validate_session(session_id, update_activity=False) if session_id else None
    if session is None:
        raise UnauthorizedException("Your session has ended. Sign in again.")
    status = await service.status(db, session)
    await db.commit()
    return status


@router.post(
    "/auth/session/renew",
    response_model=SessionStatus,
    summary="Stay logged in: slide the idle window without leaving the page",
    responses={401: {"description": "The session already ended"}},
)
async def renew_session(
    principal: Annotated[Principal, Depends(get_current_principal)], db: AsyncSessionDep, service: SessionServiceDep
) -> SessionStatus:
    session = await service.manager.validate_session(principal.metadata["session_id"], update_activity=False)
    if session is None:
        raise UnauthorizedException("Your session has ended. Sign in again.")
    status = await service.status(db, session)
    await db.commit()
    return status


@router.post("/auth/logout-everywhere", response_model=SessionsRevoked, summary="End every one of my sessions, on every device")
async def logout_everywhere(
    response: Response,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: AsyncSessionDep,
    service: SessionServiceDep,
    context: AuditContextDep,
) -> SessionsRevoked:
    revoked = await service.revoke_all(db, principal.user_id, context)
    service.manager.clear_session_cookies(response)
    return SessionsRevoked(revoked=revoked)


@router.delete(
    "/users/{user_id}/sessions",
    response_model=SessionsRevoked,
    summary="End every session of a user, e.g. a lost phone (Admin)",
)
async def revoke_user_sessions(
    user_id: int, db: AsyncSessionDep, service: SessionServiceDep, context: AuditContextDep, _: UserManagerDep
) -> SessionsRevoked:
    return SessionsRevoked(revoked=await service.revoke_all(db, user_id, context))


@router.get("/sessions/policy", response_model=SessionPolicyValues, summary="Session timeouts and mobile access")
async def get_session_policy(db: AsyncSessionDep, service: SessionServiceDep, _: SettingsManagerDep) -> SessionPolicyValues:
    policy = await service.policy(db)
    await db.commit()
    return SessionPolicyValues.model_validate(policy, from_attributes=True)


@router.put(
    "/sessions/policy",
    response_model=SessionPolicyValues,
    summary="Change session timeouts (new sessions only) and mobile read-only (Admin)",
)
async def put_session_policy(
    values: SessionPolicyValues,
    db: AsyncSessionDep,
    service: SessionServiceDep,
    context: AuditContextDep,
    _: SettingsManagerDep,
) -> SessionPolicyValues:
    policy = await service.set_policy(db, values, context)
    return SessionPolicyValues.model_validate(policy, from_attributes=True)
