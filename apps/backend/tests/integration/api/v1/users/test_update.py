import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from .test_create import generate_unique_user_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


async def promote_to_superuser(client: AsyncClient, username: str) -> None:
    response = await client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": True})
    assert response.status_code == 200


async def test_update_user_profile_success(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]
    update_data = {
        "name": "Updated Name",
        "email": "updated.email@example.com",
        "profile_image_url": "https://example.com/new-image.jpg",
    }

    logger.info(f"Testing successful profile update for user: {username}, user_id: {test_user['id']}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    if response.status_code != 200:
        logger.error(f"Response status: {response.status_code}, body: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "User updated successfully"

    get_response = await auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    user_data = get_response.json()
    assert user_data["name"] == update_data["name"]
    assert user_data["email"] == update_data["email"]


async def test_update_user_profile_invalid_email(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]
    update_data = {"email": "invalid-email"}

    logger.info(f"Testing invalid email update for user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_update_user_profile_unauthorized(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    username = test_user["username"]
    update_data = {"name": "Unauthorized Update"}

    logger.info("Testing unauthorized profile update")
    response = await client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 401
    data = response.json()
    assert "not authenticated" in data["detail"].lower()


async def test_update_user_profile_wrong_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    other_user_data = generate_unique_user_data("other")
    create_response = await auth_client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201
    other_username = other_user_data["username"]

    update_data = {"name": "Unauthorized Update"}
    response = await auth_client.patch(f"/api/v1/users/{other_username}", json=update_data)

    assert response.status_code == 403
    data = response.json()
    assert "permission" in data["detail"].lower()


async def test_update_user_profile_duplicate_email(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    other_user_data = generate_unique_user_data("other")
    create_response = await auth_client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201

    username = test_user["username"]
    update_data = {"email": other_user_data["email"]}

    logger.info(f"Testing duplicate email update for user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_update_user_profile_duplicate_username(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    other_user_data = generate_unique_user_data("other")
    create_response = await auth_client.post("/api/v1/users/", json=other_user_data)
    assert create_response.status_code == 201

    username = test_user["username"]
    update_data = {"username": other_user_data["username"]}

    logger.info(f"Testing duplicate username update for user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}", json=update_data)

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


async def test_update_user_role_superuser(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    second_test_role: dict,
):
    username = test_user["username"]
    update_data = {"role_id": second_test_role["id"]}

    logger.info(f"Testing role update by superuser for user: {username}")
    response = await superuser_auth_client.patch(f"/api/v1/users/{username}/role", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "User role updated successfully"

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    user_data = get_response.json()
    assert user_data["role_id"] == second_test_role["id"]
    # The name follows the id: the expression is resolved per read, never stored.
    assert user_data["role_name"] == second_test_role["name"]


async def test_update_user_role_regular_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    second_test_role: dict,
):
    username = test_user["username"]
    update_data = {"role_id": second_test_role["id"]}

    logger.info(f"Testing role update by regular user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}/role", json=update_data)

    assert response.status_code == 403
    data = response.json()
    assert any(word in data["detail"].lower() for word in ["permission", "privileges", "authorized"])


async def test_update_user_superuser_status_promotes_user(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    logger.info(f"Testing superuser promotion by superuser for user: {username}")
    response = await superuser_auth_client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": True})

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "User superuser status updated successfully"

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    assert get_response.json()["is_superuser"] is True


async def test_update_user_superuser_status_regular_user_forbidden(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    logger.info(f"Testing superuser status update rejected for regular user: {username}")
    response = await auth_client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": True})

    assert response.status_code == 403
    data = response.json()
    assert any(word in data["detail"].lower() for word in ["permission", "privileges", "authorized"])


async def test_update_user_superuser_status_anonymous(client: AsyncClient, db_session: AsyncSession, test_user: dict):
    username = test_user["username"]

    logger.info("Testing superuser status update rejected for anonymous caller")
    response = await client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": True})

    assert response.status_code == 401
    data = response.json()
    assert "not authenticated" in data["detail"].lower()


async def test_update_user_superuser_status_last_superuser_demotion_forbidden(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_superuser: dict,
):
    username = test_superuser["username"]

    logger.info(f"Testing demotion of the workspace's only superuser is blocked: {username}")
    response = await superuser_auth_client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": False})

    assert response.status_code == 403

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    assert get_response.json()["is_superuser"] is True


async def test_update_user_superuser_status_demotion_allowed_when_another_superuser_remains(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_superuser: dict,
    test_user: dict,
):
    await promote_to_superuser(superuser_auth_client, test_user["username"])

    username = test_superuser["username"]

    logger.info(f"Testing demotion succeeds for superuser: {username} while another superuser remains")
    response = await superuser_auth_client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": False})

    assert response.status_code == 200

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.status_code == 200
    assert get_response.json()["is_superuser"] is False


async def test_update_user_superuser_status_user_not_found(superuser_auth_client: AsyncClient, db_session: AsyncSession):
    response = await superuser_auth_client.patch("/api/v1/users/no-such-user/superuser", json={"is_superuser": True})

    assert response.status_code == 404


async def test_update_user_superuser_status_idempotent(
    superuser_auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    username = test_user["username"]

    first = await superuser_auth_client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": False})
    assert first.status_code == 200

    second = await superuser_auth_client.patch(f"/api/v1/users/{username}/superuser", json={"is_superuser": False})
    assert second.status_code == 200

    get_response = await superuser_auth_client.get(f"/api/v1/users/{username}")
    assert get_response.json()["is_superuser"] is False
