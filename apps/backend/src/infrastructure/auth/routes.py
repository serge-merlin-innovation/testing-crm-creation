from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from fastapi import APIRouter, Depends, Form, Request, Response

from ...modules.audit.service import AuditContext, AuditService
from ...modules.user.crud import crud_users
from ...modules.user.schemas import UserRead
from ..clock import ClockDep
from ..dependencies import AsyncSessionDep
from ..logging import get_logger
from .dependencies import get_current_principal, get_optional_principal
from .setup import auth as crud_auth

logger = get_logger()

router = APIRouter(tags=["Authentication"])

audit = AuditService()


@router.post(
    "/login",
    summary="Log in with email and password",
    description="""
            Verifies the email and password, refuses a user who holds no role, and opens a
            server-side session (HTTP-only cookie plus a CSRF token). Rate limited per IP and
            per account. Every attempt that names a known account is written to the audit log.
            """,
    responses={
        200: {"description": "Login successful, session created"},
        401: {"description": "Invalid email or password"},
        403: {"description": "The account holds no role"},
        429: {"description": "Too many login attempts, try again later"},
    },
)
async def login(
    request: Request,
    response: Response,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: AsyncSessionDep,
    clock: ClockDep,
) -> dict[str, str]:
    try:
        user = await crud_auth.authenticate_password(db, email, password, request=request)
    except UnauthorizedException:
        raise UnauthorizedException("Invalid email or password")

    user_id = crud_auth.repo.user_id(user)
    context = AuditContext.from_request(request, user_id, clock)
    profile = await crud_users.get(db=db, id=user_id, is_deleted=False, schema_to_select=UserRead)

    if not profile or profile.get("role_name") is None:
        audit.record(db, context, "login.denied", record_type="user", record_id=user_id, new_values={"reason": "no_role"})
        await db.commit()
        raise ForbiddenException("Your account has no role. Ask an administrator for access.")

    session_id, csrf_token = await crud_auth.sessions.create_session(
        request,
        user_id=user_id,
        metadata={"login_type": "password"},
    )
    audit.record(db, context, "login", record_type="user", record_id=user_id)
    await db.commit()
    crud_auth.sessions.set_session_cookies(response, session_id, csrf_token)

    return {"csrf_token": csrf_token}


@router.post(
    "/logout",
    summary="Log out",
    responses={200: {"description": "Logout successful, session terminated"}, 401: {"description": "Not authenticated"}},
)
async def logout(
    response: Response,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> dict[str, str]:
    session_id = principal.metadata.get("session_id")
    if session_id:
        await crud_auth.sessions.revoke(session_id, owner_id=principal.user_id)
    crud_auth.sessions.clear_session_cookies(response)

    return {"message": "Logged out successfully"}


@router.post(
    "/refresh-csrf",
    summary="Refresh the CSRF token",
    responses={200: {"description": "New CSRF token generated successfully"}, 401: {"description": "Not authenticated"}},
)
async def refresh_csrf_token(
    request: Request,
    response: Response,
) -> dict[str, str]:
    sessions = crud_auth.sessions
    session_id = request.cookies.get(sessions.session_cookie_name)
    session = await sessions.validate_session(session_id) if session_id else None
    if session is None or session_id is None:
        raise UnauthorizedException("Not authenticated")

    ttl_seconds = sessions.timeout_seconds_for(session.metadata)
    csrf_token = await sessions.regenerate_csrf_token(
        user_id=session.user_id, session_id=session_id, expiration_seconds=ttl_seconds
    )
    sessions.set_csrf_cookie(response, csrf_token, max_age=ttl_seconds)

    return {"csrf_token": csrf_token}


@router.get("/check-auth")
async def check_auth(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: AsyncSessionDep,
) -> dict[str, Any]:
    if principal is None:
        return {"authenticated": False, "message": "Not authenticated"}

    try:
        user = await crud_users.get(db=db, id=principal.user_id, is_deleted=False, schema_to_select=UserRead)

        if not user:
            return {"authenticated": False, "message": "User not found"}

        session_id = principal.metadata.get("session_id")
        session = await crud_auth.sessions.validate_session(session_id) if session_id else None

        return {
            "authenticated": True,
            "user": {"id": user["id"], "email": user["email"], "role_name": user.get("role_name")},
            "session": {
                "created_at": session.created_at.isoformat() if session and session.created_at else None,
                "last_activity": session.last_activity.isoformat() if session and session.last_activity else None,
            },
        }
    except Exception as e:
        logger.error(f"Error checking authentication: {str(e)}", exc_info=True)
        return {"authenticated": False, "message": "Error checking authentication status"}
