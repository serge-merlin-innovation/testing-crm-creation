import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_roles_anonymous(client: AsyncClient, test_role: dict):
    response = await client.get("/api/v1/roles/")

    assert response.status_code == 401
    assert "not authenticated" in response.json()["detail"].lower()


async def test_list_roles_regular_user(auth_client: AsyncClient, test_role: dict):
    response = await auth_client.get("/api/v1/roles/")

    assert response.status_code == 403
    detail = response.json()["detail"].lower()
    assert any(word in detail for word in ["permission", "privileges", "authorized"])


async def test_list_roles_superuser(superuser_auth_client: AsyncClient, test_role: dict):
    response = await superuser_auth_client.get("/api/v1/roles/")

    assert response.status_code == 200
    data = response.json()
    assert any(role["name"] == test_role["name"] for role in data["data"])


async def test_get_role_by_name_anonymous(client: AsyncClient, test_role: dict):
    response = await client.get(f"/api/v1/roles/{test_role['name']}")

    assert response.status_code == 401
    assert "not authenticated" in response.json()["detail"].lower()


async def test_get_role_by_name_regular_user(auth_client: AsyncClient, test_role: dict):
    response = await auth_client.get(f"/api/v1/roles/{test_role['name']}")

    assert response.status_code == 403


async def test_get_role_by_name_superuser(superuser_auth_client: AsyncClient, test_role: dict):
    response = await superuser_auth_client.get(f"/api/v1/roles/{test_role['name']}")

    assert response.status_code == 200
    assert response.json()["name"] == test_role["name"]


async def test_get_unknown_role_superuser(superuser_auth_client: AsyncClient, test_role: dict):
    response = await superuser_auth_client.get("/api/v1/roles/nonexistentrole")

    assert response.status_code == 404
