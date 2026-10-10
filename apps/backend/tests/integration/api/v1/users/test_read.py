import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_get_user_by_username_success(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: dict, test_role: dict
):
    logger.info("Testing successful user retrieval by username")
    username = test_user["username"]
    response = await auth_client.get(f"/api/v1/users/{username}")

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == username
    assert "id" in data
    assert "email" in data
    assert "name" in data
    # A genuine DB read, so this is the assertion that proves the mapped expression is selected.
    assert data["role_name"] == test_role["name"]


async def test_get_user_by_username_not_found(auth_client: AsyncClient, db_session: AsyncSession):
    logger.info("Testing 404 when user not found")
    response = await auth_client.get("/api/v1/users/nonexistentuser")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


async def test_get_users_unauthorized(client: AsyncClient, db_session: AsyncSession):
    logger.info("Testing unauthorized access to users list")
    response = await client.get("/api/v1/users/")

    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


async def test_get_users_superuser_success(superuser_auth_client: AsyncClient, db_session: AsyncSession):
    logger.info("Testing superuser access to users list")
    response = await superuser_auth_client.get("/api/v1/users/")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert "total_count" in data
    assert "page" in data
    assert "items_per_page" in data
    # The list path goes through schema_to_select, the profile path does not - both must carry it.
    assert all("role_name" in user for user in data["data"])


async def test_get_users_pagination(superuser_auth_client: AsyncClient, db_session: AsyncSession):
    logger.info("Testing users list pagination")

    response = await superuser_auth_client.get("/api/v1/users/?page=1&items_per_page=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) <= 5
    assert data["page"] == 1
    assert data["items_per_page"] == 5


async def test_get_current_user_profile(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict):
    logger.info("Testing current user profile retrieval")
    response = await auth_client.get("/api/v1/users/me")

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == test_user["username"]
    assert data["email"] == test_user["email"]
    assert data["role_name"] == test_user["role_name"]


async def test_get_current_user_profile_reads_role_name_from_the_database(
    client: AsyncClient, test_user: dict, test_role: dict
):
    logger.info("Testing current user profile role name over a real session")
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["role_name"] == test_role["name"]


async def test_get_user_role_info(auth_client: AsyncClient, db_session: AsyncSession, test_user: dict, test_role: dict):
    logger.info("Testing user role information retrieval")
    response = await auth_client.get(f"/api/v1/users/{test_user['username']}/role")

    assert response.status_code == 200
    data = response.json()
    assert "role" in data
    # This route joins `roles` into the outer FROM. Asserting both the flat name and the nested
    # one is what catches a dropped `correlate_except` (the statement stops compiling) and a
    # prefix collision (the flat key gets swallowed into the nest).
    assert data["role_name"] == test_role["name"]
    assert data["role"]["name"] == test_role["name"]
