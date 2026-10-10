import csv
import io
import time
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.role.models import Role
from src.modules.role.permissions import DEFAULT_ROLES, Permission, RoleName

from .helpers import login, make_user, role_id, step_up

pytestmark = pytest.mark.asyncio


# ROLE-01: fresh install, system starts, six roles exist with the role table's default access.
async def test_startup_seeds_the_six_roles_with_default_access(fresh_db: AsyncSession, startup_against_test_db):
    async with app.router.lifespan_context(app):
        pass

    roles = {role.name: set(role.permissions) for role in (await fresh_db.execute(select(Role))).scalars()}

    assert set(roles) == {name.value for name in RoleName}
    for name, (_, permissions) in DEFAULT_ROLES.items():
        assert roles[name.value] == {permission.value for permission in permissions}
    assert not {"deals.read_staffed", "deals.edit_staffed"} & roles[RoleName.ADMIN.value]
    assert roles[RoleName.READ_ONLY.value] == {Permission.DASHBOARD_AGGREGATED.value}


async def test_seeding_twice_keeps_admin_edits(fresh_db: AsyncSession, startup_against_test_db):
    async with app.router.lifespan_context(app):
        pass
    partner = (await fresh_db.execute(select(Role).where(Role.name == RoleName.PARTNER.value))).scalar_one()
    partner.permissions = ["dashboard.firm"]
    await fresh_db.commit()

    async with app.router.lifespan_context(app):
        pass

    await fresh_db.refresh(partner)
    assert partner.permissions == ["dashboard.firm"]


# Login is by email; there is no username field anywhere.
async def test_login_is_by_email(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    by_email = await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": "Password123!"})
    by_username = await client.post("/api/v1/auth/login", data={"username": "ana", "password": "Password123!"})

    assert by_email.status_code == 200
    assert by_username.status_code == 422


async def test_microsoft_sign_in_is_gone(client: AsyncClient):
    paths = app.openapi()["paths"]

    # The NFR-05 client-credentials token endpoint (/api/v1/oauth/token) is API access, not sign-in.
    assert not [path for path in paths if path.startswith("/api/v1/auth/") and "oauth" in path or "microsoft" in path]
    assert (await client.get("/api/v1/auth/oauth/microsoft")).status_code == 404


# AUTHZ-01 criterion 1: an action outside the role's permissions is 403 on the server.
@pytest.mark.parametrize(
    ("role_name", "expected"),
    [
        (RoleName.ADMIN, 200),
        (RoleName.PARTNER, 403),
        (RoleName.DIRECTOR, 403),
        (RoleName.ANALYST, 403),
        (RoleName.COMPLIANCE, 403),
        (RoleName.READ_ONLY, 403),
    ],
)
async def test_action_outside_permissions_is_403(client: AsyncClient, seeded_db: AsyncSession, role_name, expected):
    await make_user(seeded_db, "who@firm.be", role_name)
    await login(client, "who@firm.be")

    assert (await client.get("/api/v1/roles/matrix")).status_code == expected
    assert (await client.get("/api/v1/users/")).status_code == expected


async def test_me_exposes_permissions_so_the_ui_can_hide_controls(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(client, "ana@firm.be")

    me = (await client.get("/api/v1/users/me")).json()

    assert me["role_name"] == RoleName.ANALYST.value
    assert set(me["permissions"]) == {"deals.read_staffed", "deals.edit_staffed"}
    assert "is_superuser" not in me
    assert "username" not in me


# AUTHZ-01 criterion 2: an edited role applies at the next request and is audited.
async def test_permission_edit_applies_next_request_and_is_audited(client: AsyncClient, seeded_db: AsyncSession):
    admin = await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await make_user(seeded_db, "ro@firm.be", RoleName.READ_ONLY)
    other = AsyncClient(transport=client._transport, base_url="http://test")
    await login(other, "ro@firm.be")
    assert (await other.get("/api/v1/audit/")).status_code == 403

    csrf = await login(client, "admin@firm.be")
    response = await client.put(
        f"/api/v1/roles/{await role_id(seeded_db, RoleName.READ_ONLY)}/permissions",
        json={"permissions": ["dashboard.aggregated", "audit.read"]},
        headers=csrf,
    )

    assert response.status_code == 200
    assert (await other.get("/api/v1/audit/")).status_code == 200
    entries = (await client.get("/api/v1/audit/", params={"action": "role.permissions_changed"})).json()["data"]
    assert len(entries) == 1
    assert entries[0]["user_id"] == admin["id"]
    assert entries[0]["old_values"] == {"permissions": ["dashboard.aggregated"]}
    assert entries[0]["new_values"] == {"permissions": ["audit.read", "dashboard.aggregated"]}


async def test_unknown_permission_is_rejected(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")

    response = await client.put(
        f"/api/v1/roles/{await role_id(seeded_db, RoleName.ANALYST)}/permissions",
        json={"permissions": ["deals.everything"]},
        headers=csrf,
    )

    assert response.status_code == 422


# AUTHZ-01 criterion 3 / AUTH-01: a user with no role is denied at login, and the attempt is logged.
async def test_user_without_role_is_denied_at_login(client: AsyncClient, seeded_db: AsyncSession):
    nobody = await make_user(seeded_db, "nobody@firm.be", None)

    response = await client.post("/api/v1/auth/login", data={"email": "nobody@firm.be", "password": "Password123!"})

    assert response.status_code == 403
    assert "session_id" not in response.cookies
    denied = (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "login.denied"))).scalars().all()
    assert [entry.user_id for entry in denied] == [nobody["id"]]


# AUTHZ-01 criterion 4: matrix with roles as columns, permissions as rows, exportable.
async def test_permission_matrix_has_roles_as_columns_and_exports(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await login(client, "admin@firm.be")

    matrix = (await client.get("/api/v1/roles/matrix")).json()
    assert [column["name"] for column in matrix["columns"]] == [name.value for name in RoleName]
    assert [row["permission"] for row in matrix["rows"]] == [permission.value for permission in Permission]
    audit_row = next(row for row in matrix["rows"] if row["permission"] == "audit.read")
    assert audit_row["granted"] == [True, False, False, False, True, False]

    export = await client.get("/api/v1/roles/matrix/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "attachment" in export.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(export.text)))
    assert rows[0] == ["Permission", *[name.value for name in RoleName]]
    assert rows[1 + list(Permission).index(Permission.AUDIT_READ)] == ["audit.read", "x", "", "", "", "x", ""]
    exports = (await client.get("/api/v1/audit/", params={"action": "export"})).json()["data"]
    assert exports[0]["record_type"] == "permission_matrix"


# AUTHZ-01 criterion 5: one role per user; a second role is blocked.
async def test_assigning_a_second_role_is_blocked(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    csrf = await login(client, "admin@firm.be")

    response = await client.post(
        f"/api/v1/users/{ana['id']}/roles",
        json={"role_id": await role_id(seeded_db, RoleName.DIRECTOR)},
        headers=csrf,
    )

    assert response.status_code == 409
    me = (await client.get(f"/api/v1/users/{ana['id']}")).json()
    assert me["role_name"] == RoleName.ANALYST.value


async def test_a_first_role_can_be_assigned(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    new = await make_user(seeded_db, "new@firm.be", None)
    csrf = await login(client, "admin@firm.be")

    response = await client.post(
        f"/api/v1/users/{new['id']}/roles",
        json={"role_id": await role_id(seeded_db, RoleName.ANALYST)},
        headers=csrf,
    )

    assert response.status_code == 200


# ADM-02 criterion 1: Analyst to Director applies at the next request, audited with old and new.
async def test_role_change_applies_next_request_and_is_audited(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    ana_client = AsyncClient(transport=client._transport, base_url="http://test")
    await login(ana_client, "ana@firm.be")
    assert "deal_team.assign" not in (await ana_client.get("/api/v1/users/me")).json()["permissions"]

    csrf = await login(client, "admin@firm.be")
    response = await client.patch(
        f"/api/v1/users/{ana['id']}/role",
        json={"role_id": await role_id(seeded_db, RoleName.DIRECTOR)},
        headers=step_up("admin@firm.be", csrf),
    )

    assert response.status_code == 200
    assert "deal_team.assign" in (await ana_client.get("/api/v1/users/me")).json()["permissions"]
    entries = (await client.get("/api/v1/audit/", params={"record_type": "user", "record_id": str(ana["id"])})).json()
    change = next(entry for entry in entries["data"] if entry["action"] == "user.role_changed")
    assert change["old_values"] == {"role": RoleName.ANALYST.value}
    assert change["new_values"] == {"role": RoleName.DIRECTOR.value}


# ADM-02 criterion 2: removing the last Admin is blocked.
async def test_removing_the_last_admin_is_blocked(client: AsyncClient, seeded_db: AsyncSession):
    admin = await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")

    demote = await client.patch(
        f"/api/v1/users/{admin['id']}/role",
        json={"role_id": await role_id(seeded_db, RoleName.PARTNER)},
        headers=step_up("admin@firm.be", csrf),
    )
    deactivate = await client.delete(f"/api/v1/users/{admin['id']}", headers=csrf)

    assert demote.status_code == 403
    assert deactivate.status_code == 403
    assert (await client.get("/api/v1/users/me")).json()["role_name"] == RoleName.ADMIN.value
    changes = (await client.get("/api/v1/audit/", params={"action": "user.role_changed"})).json()["data"]
    assert changes == []


async def test_a_second_admin_can_be_demoted(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    other = await make_user(seeded_db, "admin2@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")

    response = await client.patch(
        f"/api/v1/users/{other['id']}/role",
        json={"role_id": await role_id(seeded_db, RoleName.PARTNER)},
        headers=step_up("admin@firm.be", csrf),
    )

    assert response.status_code == 200


async def test_admin_role_cannot_lose_the_permissions_that_manage_roles(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")

    response = await client.put(
        f"/api/v1/roles/{await role_id(seeded_db, RoleName.ADMIN)}/permissions",
        json={"permissions": ["audit.read"]},
        headers=csrf,
    )

    assert response.status_code == 403


# AUD-01 criterion 1: user, time, IP, record and old/new values are logged for logins and changes.
async def test_audit_entries_carry_user_time_ip_record_and_values(client: AsyncClient, seeded_db: AsyncSession):
    admin = await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")
    created = await client.post(
        "/api/v1/users/",
        json={
            "first_name": "New",
            "last_name": "Hire",
            "email": "hire@firm.be",
            "role_id": await role_id(seeded_db, RoleName.PARTNER),
        },
        headers=csrf,
    )
    assert created.status_code == 201, created.text
    hire_id = created.json()["id"]
    await client.patch(f"/api/v1/users/{hire_id}", json={"name": "New Name"}, headers=csrf)
    await client.patch(
        f"/api/v1/users/{hire_id}/role",
        json={"role_id": await role_id(seeded_db, RoleName.ANALYST)},
        headers=step_up("admin@firm.be", csrf),
    )
    await client.delete(f"/api/v1/users/{hire_id}", headers=csrf)

    entries = (await client.get("/api/v1/audit/", params={"user_id": admin["id"]})).json()["data"]
    by_action = {entry["action"]: entry for entry in entries}

    assert {"login", "user.created", "user.updated", "user.role_changed", "user.deleted"} <= set(by_action)
    for entry in entries:
        assert entry["user_id"] == admin["id"]
        assert entry["ip_address"]
        assert entry["created_at"]
    assert by_action["login"]["record_type"] == "user"
    assert by_action["user.created"]["record_id"] == str(hire_id)
    assert by_action["user.created"]["new_values"]["email"] == "hire@firm.be"
    assert by_action["user.updated"]["old_values"] == {"name": "New Hire"}
    assert by_action["user.updated"]["new_values"] == {"name": "New Name"}
    assert by_action["user.deleted"]["old_values"] == {"is_deleted": False}


async def test_audit_entry_records_the_forwarded_client_ip(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await login(client, "admin@firm.be")

    entries = (await client.get("/api/v1/audit/", params={"action": "login"})).json()["data"]

    assert entries[0]["ip_address"] == "127.0.0.1"


# AUD-01 criterion 2: append-only, retained 10 years.
async def test_audit_log_rows_cannot_be_updated_or_deleted(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await login(client, "admin@firm.be")

    for statement in ("UPDATE audit_log SET action = 'tampered'", "DELETE FROM audit_log", "TRUNCATE audit_log"):
        with pytest.raises(DBAPIError, match="append-only"):
            await seeded_db.execute(text(statement))
        await seeded_db.rollback()

    assert (await seeded_db.execute(select(AuditEntry.action).order_by(AuditEntry.id))).scalars().all() == [
        "user.2fa_enrolled",
        "login",
    ]


async def test_audit_api_offers_no_edit_or_delete(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    csrf = await login(client, "admin@firm.be")
    entry_id = (await client.get("/api/v1/audit/")).json()["data"][0]["id"]

    for method in ("PUT", "PATCH", "DELETE"):
        response = await client.request(method, f"/api/v1/audit/{entry_id}", headers=csrf, json={})
        assert response.status_code in (404, 405)


async def test_audit_entries_are_retained_ten_years(client: AsyncClient, seeded_db: AsyncSession):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await login(client, "admin@firm.be")

    entry = (await client.get("/api/v1/audit/", params={"action": "login"})).json()["data"][0]
    entry_row = (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "login"))).scalar_one()

    assert entry["retain_until"]
    assert entry_row.retain_until - entry_row.created_at >= timedelta(days=3652)


# AUD-01 criterion 3: compliance searches by user or record in under 5 seconds.
async def test_compliance_searches_by_user_and_record_fast(client: AsyncClient, seeded_db: AsyncSession):
    compliance = await make_user(seeded_db, "comp@firm.be", RoleName.COMPLIANCE)
    await seeded_db.execute(
        text(
            "INSERT INTO audit_log (user_id, action, record_type, record_id, ip_address, created_at, retain_until) "
            "SELECT (g % 50) + 1000, 'deal.viewed', 'deal', (g % 2000)::text, '10.0.0.1', now(), now() + interval '10 years' "
            "FROM generate_series(1, 50000) AS g"
        )
    )
    await seeded_db.commit()
    await login(client, "comp@firm.be")

    started = time.perf_counter()
    by_user = await client.get("/api/v1/audit/", params={"user_id": 1007, "items_per_page": 100})
    by_record = await client.get("/api/v1/audit/", params={"record_type": "deal", "record_id": "42"})
    elapsed = time.perf_counter() - started

    assert by_user.status_code == 200
    assert by_user.json()["total_count"] == 1000
    assert all(entry["user_id"] == 1007 for entry in by_user.json()["data"])
    assert by_record.json()["total_count"] == 25
    assert elapsed < 5
    assert compliance["id"]
