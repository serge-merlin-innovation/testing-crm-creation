from unittest.mock import patch

import pytest
from crudauth import Principal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import get_optional_principal
from src.interfaces.main import app
from src.modules.role.permissions import RoleName
from tests.integration.foundation.helpers import PASSWORD, login, make_user

pytestmark = pytest.mark.asyncio


async def test_login_success_sets_session_cookie(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    csrf = await login(client, "ana@firm.be")

    assert csrf["X-CSRF-Token"]
    assert "session_id" in client.cookies


async def test_login_email_is_case_insensitive(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    response = await client.post("/api/v1/auth/login", data={"email": "ANA@firm.be", "password": PASSWORD})

    assert response.status_code == 200


@pytest.mark.parametrize(("email", "password"), [("ana@firm.be", "wrong-password"), ("nobody@firm.be", PASSWORD)])
async def test_wrong_email_or_password_gives_one_message(client: AsyncClient, seeded_db: AsyncSession, email, password):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    response = await client.post("/api/v1/auth/login", data={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_login_soft_deleted_user_rejected(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "gone@firm.be", RoleName.ANALYST)
    admin_client = AsyncClient(transport=client._transport, base_url="http://test")
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(admin_client, "admin@firm.be")
    gone_id = (await admin_client.get("/api/v1/users/")).json()["data"][0]["id"]
    assert (await admin_client.delete(f"/api/v1/users/{gone_id}", headers=csrf)).status_code == 200

    response = await client.post("/api/v1/auth/login", data={"email": "gone@firm.be", "password": PASSWORD})

    assert response.status_code == 401


async def test_repeated_failed_logins_are_rate_limited(client: AsyncClient, seeded_db: AsyncSession):
    # An unknown account, so the per-account lock (423) cannot answer first.
    statuses = [
        (await client.post("/api/v1/auth/login", data={"email": "ghost@firm.be", "password": "wrong"})).status_code
        for _ in range(10)
    ]

    assert 429 in statuses, f"Ten failed logins in a row were never rate limited: {statuses}"
    locked_out = await client.post("/api/v1/auth/login", data={"email": "ghost@firm.be", "password": PASSWORD})
    assert locked_out.status_code == 429
    assert locked_out.headers.get("retry-after")


async def test_login_then_logout(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    csrf = await login(client, "ana@firm.be")

    logout = await client.post("/api/v1/auth/logout", headers=csrf)

    assert logout.status_code == 200
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_logout_unauthenticated_returns_401(client: AsyncClient):
    assert (await client.post("/api/v1/auth/logout")).status_code == 401


async def test_logout_without_csrf_token_rejected(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(client, "ana@firm.be")

    assert (await client.post("/api/v1/auth/logout")).status_code == 403


async def test_refresh_csrf_token(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(client, "ana@firm.be")

    response = await client.post("/api/v1/auth/refresh-csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]


async def test_refresh_csrf_token_no_session_returns_401(client: AsyncClient):
    assert (await client.post("/api/v1/auth/refresh-csrf")).status_code == 401


async def test_check_auth_authenticated(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(client, "ana@firm.be")

    body = (await client.get("/api/v1/auth/check-auth")).json()

    assert body["authenticated"] is True
    assert body["user"]["email"] == "ana@firm.be"
    assert body["user"]["role_name"] == RoleName.ANALYST.value
    assert "username" not in body["user"]


async def test_check_auth_no_session_cookie_returns_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/check-auth")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False


async def test_check_auth_user_not_found(client: AsyncClient):
    app.dependency_overrides[get_optional_principal] = lambda: Principal(user_id=999999, metadata={"session_id": "x"})
    with patch("src.modules.user.crud.crud_users.get", return_value=None):
        response = await client.get("/api/v1/auth/check-auth")

    assert response.json() == {"authenticated": False, "message": "User not found"}
