from typing import Annotated, Any

from crudauth import Principal
from crudauth.exceptions import UnauthorizedException
from crudauth.oauth import OAuthState
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from ...modules.user.crud import crud_users
from ...modules.user.enums import OAuthProvider
from ..config.settings import settings
from ..dependencies import AsyncSessionDep, OAuth2FormDep
from ..logging import get_logger
from .dependencies import get_current_principal, get_optional_principal
from .oauth import OAUTH_STATE_TTL_SECONDS, oauth_providers, oauth_state_storage
from .setup import auth as crud_auth

logger = get_logger()

router = APIRouter(tags=["Authentication"])

LOGIN_PATH = "/login"


class MicrosoftAccountNotLinkedError(Exception):
    pass


def _safe_return_path(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def _frontend_url(path: str) -> str:
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        path = "/"
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


def _microsoft_error_redirect(reason: str) -> RedirectResponse:
    return RedirectResponse(
        url=_frontend_url(f"{LOGIN_PATH}?error=oauth_error&provider={OAuthProvider.MICROSOFT.value}&reason={reason}"),
        status_code=status.HTTP_302_FOUND,
    )


@router.post(
    "/login",
    summary="User Login",
    description="""
            Authenticates a user and creates a new session.

            This endpoint accepts username/email and password credentials and verifies them.
            On successful authentication:
            - A new session is created
            - A session ID is set as an HTTP-only cookie
            - A CSRF token is generated for protection against CSRF attacks

            The endpoint is protected by rate limiting to prevent brute force attacks.
            After multiple failed attempts, further login attempts will be temporarily blocked.
            """,
    responses={
        200: {"description": "Login successful, session created"},
        401: {"description": "Authentication failed"},
        429: {"description": "Too many login attempts, try again later"},
    },
    response_description="CSRF token for use in subsequent requests",
)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2FormDep,
    db: AsyncSessionDep,
) -> dict[str, str]:
    user = await crud_auth.authenticate_password(db, form_data.username, form_data.password, request=request)

    session_id, csrf_token = await crud_auth.sessions.create_session(
        request,
        user_id=crud_auth.repo.user_id(user),
        metadata={"login_type": "password", "username": crud_auth.repo.get(user, "username")},
    )
    crud_auth.sessions.set_session_cookies(response, session_id, csrf_token)

    return {"csrf_token": csrf_token}


@router.post(
    "/logout",
    summary="User Logout",
    description="""
            Terminates the current user session.

            This endpoint:
            - Invalidates the active session in the storage backend
            - Clears all session-related cookies from the client

            After logout, the user will need to authenticate again to access
            protected resources. Any existing session tokens will no longer be valid.
            """,
    responses={200: {"description": "Logout successful, session terminated"}, 401: {"description": "Not authenticated"}},
    response_description="Confirmation of successful logout",
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
    summary="Refresh CSRF Token",
    description="""
            Generates a new CSRF token for the current session.

            This endpoint should be called to obtain a fresh CSRF token when:
            - The current token is about to expire
            - After a certain period of inactivity
            - When increased security is needed for sensitive operations

            The new token is returned in the response and also set as a cookie.
            """,
    responses={200: {"description": "New CSRF token generated successfully"}, 401: {"description": "Not authenticated"}},
    response_description="The new CSRF token for the session",
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


@router.get(
    "/oauth/microsoft",
    summary="Initiate Microsoft OAuth Login",
    description="""
            Starts the OAuth 2.0 authentication flow with Microsoft Entra ID.

            Returns the authorization URL the client should navigate to. The flow
            includes a server-side state parameter for CSRF protection and a PKCE
            code challenge. `prompt=select_account` is requested so a user on a
            shared machine can choose which Microsoft account to use.

            An optional redirect_uri controls where the user lands after the whole
            flow completes. It must be a path on the configured frontend origin;
            anything else is replaced with "/".

            Sign-in only succeeds for users whose `microsoft_id` is already set on
            their user record - this endpoint never provisions an account.
            """,
    responses={
        200: {"description": "Authorization URL generated successfully"},
        500: {"description": "Failed to initiate Microsoft login"},
    },
    response_description="The Microsoft authorization URL to redirect the user to",
)
async def oauth_microsoft_login(
    request: Request,
    redirect_uri: str | None = Query(None),
) -> dict[str, str]:
    try:
        auth_data = oauth_providers["microsoft"].get_authorization_url(
            extra_params={"prompt": "select_account"},
        )
        state_obj = OAuthState(
            state=auth_data["state"],
            provider=OAuthProvider.MICROSOFT.value,
            # Store the sanitized local path, not the raw parameter, so a bad value
            # cannot survive in the state store until the callback reads it.
            redirect_to=_safe_return_path(redirect_uri),
            code_verifier=auth_data.get("code_verifier"),
        )
        await oauth_state_storage.create(state_obj, session_id=auth_data["state"], expiration=OAUTH_STATE_TTL_SECONDS)
        return {"url": auth_data["url"]}
    except Exception as e:
        logger.error(f"Error initiating Microsoft OAuth: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate Microsoft login")


@router.get(
    "/oauth/callback/microsoft",
    summary="Microsoft OAuth Callback Handler",
    description="""
            Processes the authentication callback from Microsoft Entra ID.

            Validates the state parameter, exchanges the authorization code (with the
            stored PKCE verifier) for tokens, reads the profile from Microsoft Graph,
            and resolves it to an existing user by `microsoft_id`.

            Resolution is lookup-only. An identity with no linked user - or one linked
            to a soft-deleted user - is refused with reason `not_provisioned`; no
            account is created and the email address is never used to link. An
            account is linked when `microsoft_id` is set directly on the user record
            to the user's Entra object id.

            Two response formats are supported: `redirect` (default) sends the browser
            back to the frontend, `json` returns the user and CSRF token for SPA or
            mobile clients.
            """,
    responses={
        200: {"description": "Authentication successful (JSON response)"},
        302: {"description": "Authentication successful (redirect response)"},
        400: {"description": "Invalid OAuth state or provider mismatch"},
        403: {"description": "Microsoft account is not linked to a user"},
        500: {"description": "Server error during authentication"},
    },
    response_description="Authentication result with session cookies set",
)
async def oauth_microsoft_callback(
    request: Request,
    response: Response,
    db: AsyncSessionDep,
    code: str = Query(...),
    state: str = Query(...),
    response_format: str = Query("redirect", description="Response format, either 'redirect' or 'json'"),
):
    state_data = await oauth_state_storage.get(state, OAuthState)

    if not state_data:
        logger.warning(f"Invalid OAuth state in Microsoft callback: {state}")
        if response_format == "json":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
        return _microsoft_error_redirect("invalid_state")

    if state_data.provider != OAuthProvider.MICROSOFT.value:
        logger.warning(f"Provider mismatch in OAuth callback: expected microsoft, got {state_data.provider}")
        if response_format == "json":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider mismatch")
        return _microsoft_error_redirect("provider_mismatch")

    try:
        provider = oauth_providers["microsoft"]
        token_data = await provider.exchange_code(code, code_verifier=state_data.code_verifier)
        user_info_raw = await provider.get_user_info(token_data["access_token"])
        user_info = await provider.process_user_info(user_info_raw)

        # Lookup-only: an unknown identity is refused, never given a new account. Accounts
        # are created only by administrators. get_by_oauth does not filter
        # soft-deleted rows, and unlike password login this path has no disabled-account
        # guard, so check is_deleted explicitly.
        user = await crud_auth.repo.get_by_oauth(db, OAuthProvider.MICROSOFT.value, user_info.provider_user_id)
        if user is None or getattr(user, "is_deleted", False):
            raise MicrosoftAccountNotLinkedError(user_info.provider_user_id)

        user_id = crud_auth.repo.user_id(user)
        username = crud_auth.repo.get(user, "username")

        session_id, csrf_token = await crud_auth.sessions.create_session(
            request,
            user_id=user_id,
            metadata={
                "login_type": "oauth",
                "oauth_provider": OAuthProvider.MICROSOFT.value,
                "username": username,
            },
        )

        await oauth_state_storage.delete(state)

        if response_format == "json":
            crud_auth.sessions.set_session_cookies(response, session_id, csrf_token)
            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "username": username,
                    "email": crud_auth.repo.get(user, "email"),
                },
                "csrf_token": csrf_token,
            }

        redirect_response = RedirectResponse(
            url=_frontend_url(str(state_data.redirect_to) if state_data.redirect_to else "/"),
            status_code=status.HTTP_302_FOUND,
        )
        crud_auth.sessions.set_session_cookies(redirect_response, session_id, csrf_token)
        return redirect_response

    except MicrosoftAccountNotLinkedError as e:
        # Log the object id, not the email - it is the value an admin needs to link.
        logger.warning(f"Microsoft sign-in refused, no linked user for Entra object id {str(e)}")
        if response_format == "json":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This Microsoft account is not linked to a user. Ask an administrator to link it.",
            )
        return _microsoft_error_redirect("not_provisioned")

    except Exception as e:
        logger.error(f"Error in Microsoft OAuth callback: {str(e)}", exc_info=True)

        if response_format == "json":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OAuth authentication failed: {str(e)}"
            )

        # Deliberately no exception detail in the URL - it would leak internals to the browser.
        return _microsoft_error_redirect("callback_failed")


@router.get("/check-auth")
async def check_auth(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
    db: AsyncSessionDep,
) -> dict[str, Any]:
    if principal is None:
        return {"authenticated": False, "message": "Not authenticated"}

    try:
        user = await crud_users.get(db=db, id=principal.user_id, is_deleted=False)

        if not user:
            return {"authenticated": False, "message": "User not found"}

        session_id = principal.metadata.get("session_id")
        session = await crud_auth.sessions.validate_session(session_id) if session_id else None

        return {
            "authenticated": True,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "oauth_provider": user.get("oauth_provider"),
            },
            "session": {
                "created_at": session.created_at.isoformat() if session and session.created_at else None,
                "last_activity": session.last_activity.isoformat() if session and session.last_activity else None,
            },
        }
    except Exception as e:
        logger.error(f"Error checking authentication: {str(e)}", exc_info=True)
        return {"authenticated": False, "message": "Error checking authentication status"}
