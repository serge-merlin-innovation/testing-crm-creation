import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.permissions import RoleName
from tests.integration.foundation.helpers import login, make_user, role_id

pytestmark = pytest.mark.asyncio


async def test_anonymous_cannot_list_or_create_users(client: AsyncClient, seeded_db: AsyncSession):
    assert (await client.get("/api/v1/users/")).status_code == 401
    created = await client.post(
        "/api/v1/users/", json={"first_name": "Eve", "last_name": "X", "email": "eve@x.be", "role_id": 1}
    )
    assert created.status_code in (401, 403)


async def test_admin_creates_lists_and_paginates_users(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")
    analyst = await role_id(seeded_db, RoleName.ANALYST)
    for index in range(3):
        response = await client.post(
            "/api/v1/users/",
            json={"first_name": "Hire", "last_name": str(index), "email": f"hire{index}@firm.be", "role_id": analyst},
            headers=csrf,
        )
        assert response.status_code == 201

    page = (await client.get("/api/v1/users/", params={"items_per_page": 2})).json()

    assert page["total_count"] == 4
    assert len(page["data"]) == 2
    assert page["has_more"] is True


async def test_duplicate_email_is_409(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")

    response = await client.post(
        "/api/v1/users/",
        json={
            "first_name": "Again",
            "last_name": "X",
            "email": "admin@firm.be",
            "role_id": await role_id(seeded_db, RoleName.ANALYST),
        },
        headers=csrf,
    )

    assert response.status_code == 409


async def test_create_rejects_username_field(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")

    response = await client.post(
        "/api/v1/users/",
        json={"first_name": "Hire", "last_name": "X", "username": "hire", "email": "hire@firm.be", "role_id": 1},
        headers=csrf,
    )

    assert response.status_code == 422


async def test_user_updates_own_profile_but_not_others(client: AsyncClient, seeded_db: AsyncSession):
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    bob = await make_user(seeded_db, "bob@firm.be", RoleName.ANALYST)
    csrf = await login(client, "ana@firm.be")

    own = await client.patch(f"/api/v1/users/{ana['id']}", json={"name": "Ana Peeters"}, headers=csrf)
    other = await client.patch(f"/api/v1/users/{bob['id']}", json={"name": "Hacked"}, headers=csrf)
    read_other = await client.get(f"/api/v1/users/{bob['id']}")

    assert own.status_code == 200
    assert own.json()["name"] == "Ana Peeters"
    assert other.status_code == 403
    assert read_other.status_code == 403


async def test_non_admin_cannot_change_roles_or_deactivate(client: AsyncClient, seeded_db: AsyncSession):
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    csrf = await login(client, "ana@firm.be")

    assert (await client.patch(f"/api/v1/users/{ana['id']}/role", json={"role_id": 1}, headers=csrf)).status_code == 403
    assert (await client.delete(f"/api/v1/users/{ana['id']}", headers=csrf)).status_code == 403


async def test_admin_anonymises_a_user(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    leaver = await make_user(seeded_db, "leaver@firm.be", RoleName.ANALYST)
    csrf = await login(client, "admin@firm.be")

    response = await client.delete(f"/api/v1/users/{leaver['id']}/personal-data", headers=csrf)

    assert response.status_code == 200
    assert (await client.get(f"/api/v1/users/{leaver['id']}")).status_code == 404
    entries = (await client.get("/api/v1/audit/", params={"action": "user.anonymized"})).json()["data"]
    assert entries[0]["record_id"] == str(leaver["id"])


async def test_unknown_role_is_404(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    csrf = await login(client, "admin@firm.be")

    response = await client.patch(f"/api/v1/users/{ana['id']}/role", json={"role_id": 99999}, headers=csrf)

    assert response.status_code == 404


async def test_admin_lists_roles_in_role_table_order(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await login(client, "admin@firm.be")

    roles = (await client.get("/api/v1/roles/")).json()

    assert [role["name"] for role in roles] == [name.value for name in RoleName]
