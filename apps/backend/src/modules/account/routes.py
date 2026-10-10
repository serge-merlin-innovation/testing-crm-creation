from typing import Annotated, Any

from crudauth import Principal
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from ...infrastructure.auth.dependencies import get_current_principal
from ...infrastructure.auth.http_exceptions import HTTPException
from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import require_permission
from ..role.permissions import Permission
from ..security.dependencies import SecurityServiceDep, StepUpUserDep
from ..security.schemas import SecondFactorRequired
from ..security.service import issue_challenge
from ..security.totp import qr_svg
from ..user.dependencies import UserServiceDep
from ..user.schemas import UserCreate, UserRead
from .dependencies import AccountServiceDep
from .directory import list_users, to_csv
from .policy import current_policy
from .schemas import (
    ChangePassword,
    ForgotPassword,
    ImportResult,
    InvitationRead,
    PasswordPolicyRead,
    PasswordPolicyUpdate,
    SetPassword,
    UserList,
)
from .service import INVITE, AccountService, LinkRefusedError, TooManyResetRequestsError

users_router = APIRouter(tags=["Users"])
auth_router = APIRouter(tags=["Authentication"])
policy_router = APIRouter(tags=["Authentication"])

UserManagerDep = Annotated[dict[str, Any], require_permission(Permission.USERS_MANAGE)]
SettingsManagerDep = Annotated[dict[str, Any], require_permission(Permission.SETTINGS_MANAGE)]
Status = Annotated[str | None, Query(pattern="^(invited|active|inactive)$")]

FORGOT_MESSAGE = "If an account exists for this email, we sent a link to reset the password. It is valid for 30 minutes."
REFUSED = {
    INVITE: "This invitation link has expired or was already used. Ask your administrator to resend it.",
    "reset": "This reset link has expired or was already used. Ask for a new one from the login page.",
}


def _gone(error: LinkRefusedError) -> HTTPException:
    return HTTPException(status_code=410, detail=REFUSED[str(error)])


@users_router.post(
    "/",
    status_code=201,
    response_model=UserRead,
    summary="Invite a user (Admin)",
    description="Creates the account as Invited and sends the invitation and welcome emails.",
    responses={403: {"description": "Requires users.manage"}, 409: {"description": "Email already exists"}},
)
async def create_user(
    values: UserCreate,
    db: AsyncSessionDep,
    service: AccountServiceDep,
    user_service: UserServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
) -> dict[str, Any]:
    return await user_service.get_by_id(await service.invite(db, values, context), db)


@users_router.post("/import", response_model=ImportResult, summary="Invite users from a CSV (Admin)")
async def import_users(
    db: AsyncSessionDep,
    service: AccountServiceDep,
    context: AuditContextDep,
    _: UserManagerDep,
    file: Annotated[UploadFile, File(description="Columns: first_name,last_name,email,title,role")],
) -> dict[str, Any]:
    content = (await file.read()).decode("utf-8", errors="replace")
    return {"rows": await service.import_csv(db, content, context)}


@users_router.get("/", response_model=UserList, summary="List users with role, status, last login and dormancy (Admin)")
async def get_users(
    db: AsyncSessionDep,
    clock: ClockDep,
    _: UserManagerDep,
    role_id: int | None = None,
    status: Status = None,
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    rows, total = await list_users(db, clock.now(), role_id, status, (page - 1) * items_per_page, items_per_page)
    return {
        "data": rows,
        "total_count": total,
        "has_more": page * items_per_page < total,
        "page": page,
        "items_per_page": items_per_page,
    }


@users_router.get("/export", summary="Export the filtered user list as CSV (Admin)", response_class=Response)
async def export_users(
    db: AsyncSessionDep, clock: ClockDep, _: UserManagerDep, role_id: int | None = None, status: Status = None
) -> Response:
    rows, _total = await list_users(db, clock.now(), role_id, status)
    return Response(
        content=to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="users.csv"'},
    )


@users_router.post("/{user_id}/invitation", status_code=204, summary="Resend the invitation (Admin)")
async def resend_invitation(
    user_id: int, db: AsyncSessionDep, service: AccountServiceDep, context: AuditContextDep, _: UserManagerDep
) -> None:
    await service.resend_invitation(db, user_id, context)


@users_router.post(
    "/me/password",
    status_code=204,
    summary="Change my password",
    description="Needs the current password and the current 2FA code in X-Step-Up-Code. Ends my other sessions.",
)
async def change_password(
    values: ChangePassword,
    db: AsyncSessionDep,
    service: AccountServiceDep,
    context: AuditContextDep,
    current_user: StepUpUserDep,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> None:
    await service.change_password(
        db, current_user["id"], values.current_password, values.new_password, context, principal.metadata.get("session_id")
    )


@auth_router.get("/invitations", response_model=InvitationRead, summary="Who an invitation link is for")
async def read_invitation(token: str, db: AsyncSessionDep, service: AccountServiceDep, clock: ClockDep) -> InvitationRead:
    try:
        user = await service.invitation(db, token, clock.now())
    except LinkRefusedError as error:
        raise _gone(error) from error
    return InvitationRead(email=user.email, first_name=user.first_name, last_name=user.last_name)


@auth_router.post(
    "/invitations/accept",
    response_model=SecondFactorRequired,
    summary="Set my password from the invitation, then enrol 2FA",
    description="Returns the enrolment step; finish with POST /auth/login/second-factor.",
    responses={410: {"description": "Expired or already used"}, 422: {"description": "Password breaks the policy"}},
)
async def accept_invitation(
    values: SetPassword,
    db: AsyncSessionDep,
    service: AccountServiceDep,
    security: SecurityServiceDep,
    context: AuditContextDep,
) -> SecondFactorRequired:
    try:
        user = await service.accept_invitation(db, values.token, values.password, context)
    except LinkRefusedError as error:
        raise _gone(error) from error
    uri = await security.start_enrolment(db, user)
    await db.commit()
    return SecondFactorRequired(
        step="enrol", challenge=issue_challenge(user.id, context.clock.now()), otpauth_uri=uri, qr_svg=qr_svg(uri)
    )


@auth_router.post(
    "/password/forgot",
    status_code=202,
    summary="Ask for a password reset link",
    description="Answers the same whether or not the account exists. Three requests per email per hour.",
    responses={429: {"description": "More than 3 requests in an hour"}},
)
async def forgot_password(
    values: ForgotPassword, db: AsyncSessionDep, service: AccountServiceDep, context: AuditContextDep
) -> dict[str, str]:
    try:
        await service.request_reset(db, values.email, context)
    except TooManyResetRequestsError as error:
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again in an hour.") from error
    return {"message": FORGOT_MESSAGE}


@auth_router.post(
    "/password/reset",
    status_code=204,
    summary="Set a new password from a reset link",
    description="Ends every session and trusted device; the next login still asks for the 2FA code.",
    responses={410: {"description": "Expired or already used"}, 422: {"description": "Password breaks the policy"}},
)
async def reset_password(
    values: SetPassword, db: AsyncSessionDep, service: AccountServiceDep, context: AuditContextDep
) -> None:
    try:
        await service.reset_password(db, values.token, values.password, context)
    except LinkRefusedError as error:
        raise _gone(error) from error


@policy_router.get("/security/password-policy", response_model=PasswordPolicyRead, summary="Password policy")
async def get_password_policy(db: AsyncSessionDep, _: UserManagerDep) -> PasswordPolicyRead:
    policy = await current_policy(db)
    await db.commit()
    return PasswordPolicyRead(min_length=policy.min_length, history_count=policy.history_count)


@policy_router.put(
    "/security/password-policy",
    response_model=PasswordPolicyRead,
    summary="Change the password policy (Admin)",
    description="Applies at each user's next password change. Passwords never expire on a schedule (NIST SP 800-63B).",
)
async def put_password_policy(
    values: PasswordPolicyUpdate, db: AsyncSessionDep, context: AuditContextDep, _: SettingsManagerDep
) -> PasswordPolicyRead:
    policy = await current_policy(db)
    old = {"min_length": policy.min_length, "history_count": policy.history_count}
    for key, value in values.model_dump(exclude_none=True).items():
        setattr(policy, key, value)
    new = {"min_length": policy.min_length, "history_count": policy.history_count}
    AccountService().audit.record(
        db,
        context,
        "security.password_policy_changed",
        record_type="password_policy",
        record_id=1,
        old_values=old,
        new_values=new,
    )
    await db.commit()
    return PasswordPolicyRead(**new)
