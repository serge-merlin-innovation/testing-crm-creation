import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.dependencies import get_current_superuser, get_current_user
from src.interfaces.main import app

from .test_create import generate_unique_user_data
from .test_update import promote_to_superuser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def test_soft_delete_success(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    logger.info(f"Testing soft deletion for user: {username}")
    response = await auth_client.delete(f"/api/v1/users/{username}")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "User account deactivated"

    get_response = await auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 404


async def test_soft_delete_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    response = await client.delete(f"/api/v1/users/{username}")

    assert response.status_code == 401
    data = response.json()
    assert "not authenticated" in data["detail"].lower()


async def test_soft_delete_wrong_user(
    auth_client: AsyncClient,
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    other_user_data = generate_unique_user_data("other")
    create_response = await client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201
    other_username = other_user_data["username"]

    response = await auth_client.delete(f"/api/v1/users/{other_username}")

    assert response.status_code == 403
    data = response.json()
    assert "permission" in data["detail"].lower()


async def test_soft_delete_nonexistent_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
):
    response = await auth_client.delete("/api/v1/users/nonexistentuser")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


async def test_soft_delete_last_superuser_forbidden(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_superuser: dict,
):
    username = test_superuser["username"]

    logger.info(f"Testing deactivation of the workspace's only superuser is blocked: {username}")
    response = await superuser_auth_client.delete(f"/api/v1/users/{username}")

    assert response.status_code == 403

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200


async def test_soft_delete_superuser_allowed_when_another_remains(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_superuser: dict,
    test_user: dict,
):
    await promote_to_superuser(superuser_auth_client, test_user["username"])

    username = test_superuser["username"]

    logger.info(f"Testing deactivation succeeds for superuser: {username} while another superuser remains")
    response = await superuser_auth_client.delete(f"/api/v1/users/{username}")

    assert response.status_code == 200

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 404


async def test_permanent_delete_success(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    logger.info(f"Testing permanent deletion for user: {username}")
    response = await superuser_auth_client.delete(f"/api/v1/users/db/{username}")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "User data anonymized in compliance with GDPR"

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 404


async def test_permanent_delete_unauthorized(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    response = await auth_client.delete(f"/api/v1/users/db/{username}")

    assert response.status_code == 403
    data = response.json()
    assert "insufficient privileges" in data["detail"].lower()


async def test_permanent_delete_inactive_user(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    logger.info(f"Testing soft deletion for user: {username}")

    response_soft_delete = await superuser_auth_client.delete(f"/api/v1/users/{username}")

    assert response_soft_delete.status_code == 200
    data_soft = response_soft_delete.json()
    assert data_soft["message"] == "User account deactivated"

    logger.info(f"Testing permanent deletion for user: {username}")

    response_perma_delete = await superuser_auth_client.delete(f"/api/v1/users/db/{username}")
    assert response_perma_delete.status_code == 200
    data_perma = response_perma_delete.json()
    assert data_perma["message"] == "User data anonymized in compliance with GDPR"

    get_response = await superuser_auth_client.get(f"/api/v1/users/active-and-inactive/{username}")
    assert get_response.status_code == 404


async def test_permanent_delete_last_superuser_forbidden(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_superuser: dict,
):
    username = test_superuser["username"]

    logger.info(f"Testing GDPR anonymization of the workspace's only superuser is blocked: {username}")
    response = await superuser_auth_client.delete(f"/api/v1/users/db/{username}")

    assert response.status_code == 403

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200


async def test_permanent_delete_superuser_allowed_when_another_remains(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_superuser: dict,
    test_user: dict,
):
    await promote_to_superuser(superuser_auth_client, test_user["username"])

    username = test_superuser["username"]

    logger.info(f"Testing GDPR anonymization succeeds for superuser: {username} while another superuser remains")
    response = await superuser_auth_client.delete(f"/api/v1/users/db/{username}")

    assert response.status_code == 200

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 404


async def test_permanent_delete_nonexistent_user(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
):
    response = await superuser_auth_client.delete("/api/v1/users/db/nonexistentuser")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


async def test_delete_cascade_effects(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    test_superuser: dict,
):
    # Requesting `auth_client` and `superuser_auth_client` together does not give two identities:
    # both return the same client and only overwrite `get_current_user`, so whichever is set up
    # last decides who every call in the test is. The reader here is swapped explicitly instead.
    username = test_user["username"]

    role_response = await auth_client.get(f"/api/v1/users/{username}/role")
    assert role_response.status_code == 200

    delete_response = await auth_client.delete(f"/api/v1/users/{username}")
    assert delete_response.status_code == 200

    original_deps = app.dependency_overrides.copy()
    try:
        app.dependency_overrides[get_current_user] = lambda: test_superuser
        app.dependency_overrides[get_current_superuser] = lambda: test_superuser

        role_response = await auth_client.get(f"/api/v1/users/{username}/role")
        assert role_response.status_code == 404
    finally:
        app.dependency_overrides = original_deps
