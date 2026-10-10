from typing import Annotated, Any

from crudauth import verify_password
from crudauth.exceptions import ForbiddenException, UnauthorizedException
from crudauth.transports.session.useragent import parse_user_agent
from fastapi import APIRouter, Form, Request, Response
from sqlalchemy import func, select

from ...infrastructure.auth.http_exceptions import HTTPException
from ...infrastructure.auth.setup import auth as crud_auth
from ...infrastructure.clock import ClockDep
from ...infrastructure.config.settings import settings
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..audit.service import AuditContext
from ..role.authorization import has_permission, require_permission
from ..role.permissions import Permission
from ..user.models import User
from .dependencies import SecurityServiceDep
from .schemas import (
    LoginCompleted,
    SecondFactorRequired,
    SecondFactorSubmit,
    SecurityPolicyRead,
    SecurityPolicyUpdate,
    SecurityProfile,
    TravelUpdate,
)
from .service import TRUST_DURATION, SecurityService, issue_challenge, read_challenge
from .totp import qr_svg

router = APIRouter(tags=["Authentication"])

TRUSTED_DEVICE_COOKIE = "trusted_device"
INVALID_CREDENTIALS = "Invalid email or password"
LOCKED = "This account is locked for 15 minutes after too many failed attempts. Ask an administrator to unlock it."

UserManagerDep = Annotated[dict[str, Any], require_permission(Permission.USERS_MANAGE)]


def _locked() -> HTTPException:
    return HTTPException(status_code=423, detail=LOCKED)


async def _find_user(db: AsyncSessionDep, email: str) -> User | None:
    statement = select(User).where(func.lower(User.email) == email.strip().lower())
    return (await db.execute(statement)).scalar_one_or_none()


async def _open_session(
    request: Request, response: Response, db: AsyncSessionDep, user: User, context: AuditContext, service: SecurityService
) -> str:
    device_info = parse_user_agent(request.headers.get("user-agent", "")).model_dump()
    await service.complete_login(db, user, context, device_info)
    session_id, csrf_token = await crud_auth.sessions.create_session(
        request, user_id=user.id, metadata={"login_type": "password+totp"}
    )
    await db.commit()
    crud_auth.sessions.set_session_cookies(response, session_id, csrf_token)
    return str(csrf_token)


@router.post(
    "/auth/login",
    response_model=SecondFactorRequired | LoginCompleted,
    summary="Log in with email and password, first step",
    description="Checks the password, then asks for the TOTP code (or enrolment) unless this device is trusted.",
    responses={
        401: {"description": "Invalid email or password"},
        403: {"description": "The account holds no role"},
        423: {"description": "The account is locked"},
        429: {"description": "Too many login attempts from this IP or for this account"},
    },
)
async def login(
    request: Request,
    response: Response,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: AsyncSessionDep,
    clock: ClockDep,
    service: SecurityServiceDep,
) -> SecondFactorRequired | LoginCompleted:
    now = clock.now()
    user = await _find_user(db, email)
    context = AuditContext.from_request(request, user.id if user else None, clock)

    if user is not None and service.is_locked(await service.state(db, user.id), now):
        await db.commit()
        raise _locked()

    try:
        await crud_auth.authenticate_password(db, email, password, request=request)
    except UnauthorizedException:
        if user is not None:
            reason = "inactive" if user.is_deleted and verify_password(password, user.hashed_password) else "password"
            locked = await service.record_failure(db, user, context, reason)
            await db.commit()
            if locked:
                raise _locked()
        raise UnauthorizedException(INVALID_CREDENTIALS)

    assert user is not None
    if user.role_id is None or user.role_name is None:
        locked = await service.record_failure(db, user, context, "no_role")
        await db.commit()
        if locked:
            raise _locked()
        raise ForbiddenException("Your account has no role. Ask an administrator for access.")

    if await service.is_trusted_device(db, user.id, request.cookies.get(TRUSTED_DEVICE_COOKIE), now):
        return LoginCompleted(csrf_token=await _open_session(request, response, db, user, context, service))

    state = await service.state(db, user.id)
    challenge = issue_challenge(user.id, now)
    if state.totp_enabled:
        await db.commit()
        return SecondFactorRequired(step="code", challenge=challenge)

    uri = await service.start_enrolment(db, user)
    await db.commit()
    return SecondFactorRequired(step="enrol", challenge=challenge, otpauth_uri=uri, qr_svg=qr_svg(uri))


@router.post(
    "/auth/login/second-factor",
    response_model=LoginCompleted,
    summary="Log in, second step: the TOTP or a recovery code",
    responses={401: {"description": "Wrong code or expired challenge"}, 423: {"description": "The account is locked"}},
)
async def second_factor(
    request: Request,
    response: Response,
    values: SecondFactorSubmit,
    db: AsyncSessionDep,
    clock: ClockDep,
    service: SecurityServiceDep,
) -> LoginCompleted:
    now = clock.now()
    user_id = read_challenge(values.challenge, now)
    user = await db.get(User, user_id) if user_id is not None else None
    if user is None or user.is_deleted:
        raise UnauthorizedException("Your sign-in expired. Start again.")
    context = AuditContext.from_request(request, user.id, clock)
    state = await service.state(db, user.id)
    if service.is_locked(state, now):
        raise _locked()

    if not await service.check_code(db, state, values.code, now):
        locked = await service.record_failure(db, user, context, "code")
        await db.commit()
        if locked:
            raise _locked()
        raise UnauthorizedException("Invalid authentication code")

    recovery_codes = None
    if not state.totp_enabled:
        state.totp_enabled = True
        recovery_codes = await service.issue_recovery_codes(db, user.id)
        service.audit.record(db, context, "user.2fa_enrolled", record_type="user", record_id=user.id, user_id=user.id)

    if values.trust_device and (await service.policy(db)).trusted_devices_enabled:
        token = await service.trust_device(db, user.id, now)
        response.set_cookie(
            TRUSTED_DEVICE_COOKIE,
            token,
            max_age=int(TRUST_DURATION.total_seconds()),
            httponly=True,
            secure=settings.SESSION_SECURE_COOKIES,
            samesite="lax",
        )

    csrf_token = await _open_session(request, response, db, user, context, service)
    return LoginCompleted(csrf_token=csrf_token, recovery_codes=recovery_codes)


async def _profile(db: AsyncSessionDep, service: SecurityService, user_id: int, clock: ClockDep) -> SecurityProfile:
    state = await service.state(db, user_id)
    return SecurityProfile(
        user_id=user_id,
        two_factor_enabled=state.totp_enabled,
        locked_until=state.locked_until if service.is_locked(state, clock.now()) else None,
        last_login_at=state.last_login_at,
        last_login_ip=state.last_login_ip,
        last_login_device=state.last_login_device,
        travel_from=state.travel_from,
        travel_until=state.travel_until,
        travelling=service.is_travelling(state, clock.now().date()),
    )


def _self_or_manager(current_user: dict[str, Any], user_id: int) -> None:
    if current_user["id"] != user_id and not has_permission(current_user, Permission.USERS_MANAGE):
        raise ForbiddenException("Not allowed on this user")


@router.get("/users/{user_id}/security", response_model=SecurityProfile, summary="Last login, 2FA, lock and travel state")
async def get_security_profile(
    user_id: int, db: AsyncSessionDep, current_user: CurrentUserDep, service: SecurityServiceDep, clock: ClockDep
) -> SecurityProfile:
    _self_or_manager(current_user, user_id)
    profile = await _profile(db, service, user_id, clock)
    await db.commit()
    return profile


@router.put("/users/{user_id}/travel", response_model=SecurityProfile, summary="Flag a user as travelling for a date range")
async def set_travel(
    user_id: int,
    values: TravelUpdate,
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    service: SecurityServiceDep,
    context: AuditContextDep,
    clock: ClockDep,
) -> SecurityProfile:
    _self_or_manager(current_user, user_id)
    await service.set_travel(db, user_id, values.travel_from, values.travel_until, context)
    return await _profile(db, service, user_id, clock)


@router.post("/users/{user_id}/unlock", status_code=204, summary="Unlock a locked account (Admin)")
async def unlock_user(
    user_id: int, db: AsyncSessionDep, service: SecurityServiceDep, context: AuditContextDep, _: UserManagerDep
) -> None:
    await service.unlock(db, user_id, context)


@router.post("/users/{user_id}/reset-2fa", status_code=204, summary="Reset a user's 2FA so they re-enrol (Admin)")
async def reset_two_factor(
    user_id: int, db: AsyncSessionDep, service: SecurityServiceDep, context: AuditContextDep, _: UserManagerDep
) -> None:
    await service.reset_two_factor(db, user_id, context)


@router.get("/security/policy", response_model=SecurityPolicyRead, summary="Login security policy")
async def get_policy(db: AsyncSessionDep, service: SecurityServiceDep, _: UserManagerDep) -> SecurityPolicyRead:
    policy = await service.policy(db)
    await db.commit()
    return SecurityPolicyRead(trusted_devices_enabled=policy.trusted_devices_enabled)


@router.put("/security/policy", response_model=SecurityPolicyRead, summary="Allow or forbid Trust this device (Admin)")
async def put_policy(
    values: SecurityPolicyUpdate, db: AsyncSessionDep, service: SecurityServiceDep, context: AuditContextDep, _: UserManagerDep
) -> SecurityPolicyRead:
    policy = await service.set_policy(db, values.trusted_devices_enabled, context)
    return SecurityPolicyRead(trusted_devices_enabled=policy.trusted_devices_enabled)
