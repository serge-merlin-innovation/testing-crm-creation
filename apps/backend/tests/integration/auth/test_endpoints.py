from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crudauth import Principal, get_password_hash
from crudauth.oauth import OAuthState, OAuthUserInfo
from crudauth.ratelimit import MemoryRateLimiterBackend
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import get_optional_principal
from src.infrastructure.auth.setup import auth
from src.infrastructure.config.settings import settings
from src.interfaces.main import app
from src.modules.user.models import User

ROUTES = "src.infrastructure.auth.routes"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: dict):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert any(cookie == "session_id" for cookie in response.cookies)


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: dict):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_then_logout(client: AsyncClient, test_user: dict):
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]

    logout = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert logout.status_code == 200
    assert logout.json()["message"] == "Logged out successfully"


@pytest.mark.asyncio
async def test_check_auth_authenticated(client: AsyncClient):
    mock_user = {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "oauth_provider": "microsoft",
    }

    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_optional_principal] = lambda: Principal(user_id=1, metadata={"session_id": "test-session"})

        with patch("src.modules.user.crud.crud_users.get", return_value=mock_user):
            response = await client.get("/api/v1/auth/check-auth")

        assert response.status_code == 200
        body = response.json()
        assert body["authenticated"] is True
        assert body["user"]["id"] == 1
        assert body["user"]["username"] == "testuser"
        assert body["user"]["oauth_provider"] == "microsoft"
        assert "session" in body
    finally:
        app.dependency_overrides = original_deps


@pytest.mark.asyncio
async def test_check_auth_not_authenticated(client: AsyncClient):
    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_optional_principal] = lambda: None

        response = await client.get("/api/v1/auth/check-auth")

        assert response.status_code == 200
        assert response.json()["authenticated"] is False
        assert response.json()["message"] == "Not authenticated"
    finally:
        app.dependency_overrides = original_deps


@pytest.mark.asyncio
async def test_check_auth_no_session_cookie_returns_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/check-auth")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False


@pytest.mark.asyncio
async def test_login_soft_deleted_user_rejected(client: AsyncClient, db_session: AsyncSession, test_role: dict):
    user = User(
        name="Deleted User",
        username="deleted_user",
        email="deleted@example.com",
        hashed_password=get_password_hash("Password123!"),
        role_id=test_role["id"],
    )
    user.is_deleted = True
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "deleted_user", "password": "Password123!"},
    )

    assert response.status_code == 401


@pytest.fixture
def isolated_login_limiter(monkeypatch: pytest.MonkeyPatch):
    # Every test client shares one IP and the limiter lives in process memory, so a lockout
    # left behind would throttle the other auth tests in this worker for a minute.
    monkeypatch.setattr(auth.runtime.lockout, "backend", MemoryRateLimiterBackend())


@pytest.mark.asyncio
@pytest.mark.usefixtures("isolated_login_limiter")
async def test_repeated_failed_logins_are_rate_limited(client: AsyncClient, test_user: dict):
    statuses = [
        (
            await client.post(
                "/api/v1/auth/login",
                data={"username": test_user["username"], "password": "wrong-password"},
            )
        ).status_code
        for _ in range(10)
    ]

    assert 429 in statuses, f"Ten failed logins in a row were never rate limited: {statuses}"

    locked_out = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert locked_out.status_code == 429
    assert locked_out.headers.get("retry-after")


@pytest.mark.asyncio
async def test_logout_unauthenticated_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_csrf_token_rejected(client: AsyncClient, test_user: dict):
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    # POST without the X-CSRF-Token header → crudauth CSRF guard rejects with 403.
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_csrf_token_success(client: AsyncClient, test_user: dict):
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    response = await client.post("/api/v1/auth/refresh-csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]


@pytest.mark.asyncio
async def test_refresh_csrf_token_no_session_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh-csrf")
    assert response.status_code == 401


def _microsoft_state(redirect_to: str = "/") -> OAuthState:
    return OAuthState(
        state="ms-state",
        provider="microsoft",
        redirect_to=redirect_to,
        code_verifier="ms-code-verifier",
    )


def _microsoft_provider_mock(object_id: str = "entra-oid-123") -> MagicMock:
    provider = MagicMock()
    provider.exchange_code = AsyncMock(return_value={"access_token": "tok"})
    provider.get_user_info = AsyncMock(return_value={})
    provider.process_user_info = AsyncMock(
        return_value=OAuthUserInfo(
            provider="microsoft",
            provider_user_id=object_id,
            email="alice@client.example",
            email_verified=False,
            name="Alice Adams",
        )
    )
    return provider


async def _linked_user(db_session: AsyncSession, role_id: int, object_id: str, is_deleted: bool = False) -> User:
    user = User(
        name="Alice Adams",
        username=f"alice{object_id[-5:]}",
        email=f"alice-{object_id}@client.example",
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        role_id=role_id,
        profile_image_url="https://example.com/a.jpg",
        microsoft_id=object_id,
        oauth_provider="microsoft",
    )
    user.is_deleted = is_deleted
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_oauth_microsoft_login(client: AsyncClient):
    mock_provider = MagicMock()
    mock_provider.get_authorization_url = MagicMock(
        return_value={
            "url": "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?dummy=params",
            "state": "ms-state",
            "code_verifier": "ms-code-verifier",
        }
    )
    mock_storage = MagicMock()
    mock_storage.create = AsyncMock(return_value="ms-state")

    with (
        patch(f"{ROUTES}.oauth_providers", {"microsoft": mock_provider}),
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
    ):
        response = await client.get("/api/v1/auth/oauth/microsoft")

    assert response.status_code == 200
    assert response.json()["url"] == "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?dummy=params"
    # prompt=select_account lets a user on a shared machine pick an account.
    assert mock_provider.get_authorization_url.call_args.kwargs["extra_params"] == {"prompt": "select_account"}
    mock_storage.create.assert_called_once()


@pytest.mark.asyncio
async def test_oauth_microsoft_login_sanitizes_offsite_redirect_uri(client: AsyncClient):
    mock_provider = MagicMock()
    mock_provider.get_authorization_url = MagicMock(
        return_value={"url": "https://login.microsoftonline.com/x", "state": "ms-state", "code_verifier": "v"}
    )
    mock_storage = MagicMock()
    mock_storage.create = AsyncMock(return_value="ms-state")

    with (
        patch(f"{ROUTES}.oauth_providers", {"microsoft": mock_provider}),
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
    ):
        response = await client.get(
            "/api/v1/auth/oauth/microsoft",
            params={"redirect_uri": "https://evil.example/steal"},
        )

    assert response.status_code == 200
    assert mock_storage.create.call_args.args[0].redirect_to == "/"


@pytest.mark.asyncio
async def test_oauth_microsoft_login_provider_failure_returns_500(client: AsyncClient):
    mock_provider = MagicMock()
    mock_provider.get_authorization_url = MagicMock(side_effect=RuntimeError("boom"))

    with patch(f"{ROUTES}.oauth_providers", {"microsoft": mock_provider}):
        response = await client.get("/api/v1/auth/oauth/microsoft")

    assert response.status_code == 500
    assert "boom" not in response.text


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_invalid_state(client: AsyncClient):
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=None)

    with patch(f"{ROUTES}.oauth_state_storage", mock_storage):
        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "nope"},
        )
        assert response.status_code == 302
        assert "reason=invalid_state" in response.headers["location"]

        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "nope", "response_format": "json"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_provider_mismatch(client: AsyncClient):
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(
        return_value=OAuthState(state="ms-state", provider="not-a-provider", redirect_to="/", code_verifier="v")
    )

    with patch(f"{ROUTES}.oauth_state_storage", mock_storage):
        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state"},
        )
        assert response.status_code == 302
        assert "reason=provider_mismatch" in response.headers["location"]

        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state", "response_format": "json"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_unlinked_identity_is_refused(client: AsyncClient, db_session: AsyncSession):
    before = (await db_session.execute(select(func.count()).select_from(User))).scalar()

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=_microsoft_state())
    mock_storage.delete = AsyncMock(return_value=None)

    with (
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
        patch(f"{ROUTES}.oauth_providers", {"microsoft": _microsoft_provider_mock("unknown-oid")}),
    ):
        redirect = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state"},
        )
        as_json = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state", "response_format": "json"},
        )

    assert redirect.status_code == 302
    assert "reason=not_provisioned" in redirect.headers["location"]
    assert "session_id" not in redirect.cookies

    assert as_json.status_code == 403

    after = (await db_session.execute(select(func.count()).select_from(User))).scalar()
    assert after == before, "the callback must never provision an account"
    # State is not consumed on a refusal, so a later successful link can reuse nothing
    # stale; the TTL expires it instead.
    mock_storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_soft_deleted_user_is_refused(
    client: AsyncClient, db_session: AsyncSession, test_role: dict
):
    await _linked_user(db_session, test_role["id"], "deleted-oid", is_deleted=True)

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=_microsoft_state())

    with (
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
        patch(f"{ROUTES}.oauth_providers", {"microsoft": _microsoft_provider_mock("deleted-oid")}),
    ):
        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state"},
        )

    assert response.status_code == 302
    assert "reason=not_provisioned" in response.headers["location"]
    assert "session_id" not in response.cookies


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_signs_in_linked_user(client: AsyncClient, db_session: AsyncSession, test_role: dict):
    user = await _linked_user(db_session, test_role["id"], "entra-oid-123")

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=_microsoft_state())
    mock_storage.delete = AsyncMock(return_value=None)

    with (
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
        patch(f"{ROUTES}.oauth_providers", {"microsoft": _microsoft_provider_mock("entra-oid-123")}),
    ):
        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state", "response_format": "json"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["user"]["id"] == user.id
    assert body["user"]["username"] == user.username
    assert body["csrf_token"]
    # State is single-use: consumed so a replayed callback fails the lookup.
    mock_storage.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_redirects_to_the_frontend_origin(
    client: AsyncClient, db_session: AsyncSession, test_role: dict
):
    await _linked_user(db_session, test_role["id"], "redirect-oid")

    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=_microsoft_state(redirect_to="/analytics?range=week"))
    mock_storage.delete = AsyncMock(return_value=None)

    with (
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
        patch(f"{ROUTES}.oauth_providers", {"microsoft": _microsoft_provider_mock("redirect-oid")}),
    ):
        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state"},
        )

    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.FRONTEND_BASE_URL.rstrip('/')}/analytics?range=week"
    assert "session_id" in response.cookies
    assert "csrf_token" in response.cookies


@pytest.mark.asyncio
async def test_oauth_microsoft_callback_hides_provider_errors(client: AsyncClient):
    mock_storage = MagicMock()
    mock_storage.get = AsyncMock(return_value=_microsoft_state())

    failing = MagicMock()
    failing.exchange_code = AsyncMock(side_effect=RuntimeError("token endpoint exploded"))

    with (
        patch(f"{ROUTES}.oauth_state_storage", mock_storage),
        patch(f"{ROUTES}.oauth_providers", {"microsoft": failing}),
    ):
        response = await client.get(
            "/api/v1/auth/oauth/callback/microsoft",
            params={"code": "c", "state": "ms-state"},
        )

    assert response.status_code == 302
    assert "reason=callback_failed" in response.headers["location"]
    assert "exploded" not in response.headers["location"]


@pytest.mark.asyncio
async def test_check_auth_user_not_found(client: AsyncClient):
    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_optional_principal] = lambda: Principal(user_id=999999, metadata={"session_id": "x"})

        with patch("src.modules.user.crud.crud_users.get", return_value=None):
            response = await client.get("/api/v1/auth/check-auth")

        assert response.status_code == 200
        assert response.json()["authenticated"] is False
        assert response.json()["message"] == "User not found"
    finally:
        app.dependency_overrides = original_deps
