"""Chinese-wall fixes from the feat/ma-crm review."""

from datetime import UTC, datetime

import pytest

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate
from tests.integration.foundation.helpers import step_up

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.compliance = await built.actor("cora", RoleName.COMPLIANCE)
    built.client_id = await built.company("Acme Holding")
    yield built
    await built.close()
    set_clock(SystemClock())


async def staff(world, mandate_id: int, actor, role: str = "analyst") -> None:
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/team", json={"user_id": actor.id, "role": role}, headers=world.partner.headers
    )
    assert response.status_code == 201, response.text


async def audit_rows(actor, **params) -> list[dict]:
    response = await actor.client.get("/api/v1/audit/", params={"items_per_page": 500, **params}, headers=actor.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# B1 (ROLE-01 c2, AUTHZ-02, AUTHZ-06): the audit log shows Admin no deal content and no fee rows.
async def test_audit_log_hides_deal_and_fee_rows_from_admin(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    fees = await world.partner.client.put(
        f"/api/v1/mandates/{mandate['id']}/fees",
        json={
            "retainer_monthly": "10000",
            "success_fee_kind": "percent",
            "success_fee_percent": "2",
            "minimum_fee": "0",
            "retainers_creditable": False,
        },
        headers=world.partner.headers,
    )
    assert fees.status_code == 200, fees.text

    for record_type in ("mandate", "fee_terms"):
        admin_rows = await audit_rows(world.admin, record_type=record_type)
        assert admin_rows == [], admin_rows
    assert "Falcon" not in str(await audit_rows(world.admin))
    assert await audit_rows(world.compliance, record_type="mandate")
    assert await audit_rows(world.compliance, record_type="fee_terms")


async def break_glass(world, code_name: str = "Falcon") -> None:
    response = await world.admin.client.post(
        "/api/v1/break-glass/",
        json={"code_name": code_name, "reason": "Fix corrupted EV"},
        headers=step_up(world.admin.email, world.admin.headers),
    )
    assert response.status_code == 201, response.text


# B3 (AUTHZ-08 c3): break-glass reads the buyer list but never exports it.
async def test_break_glass_cannot_export_the_buyer_list(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await break_glass(world)
    url = f"/api/v1/mandates/{mandate['id']}/buyers"
    assert (await world.admin.client.get(url, headers=world.admin.headers)).status_code == 200
    exported = await world.admin.client.get(f"{url}/export", headers=world.admin.headers)
    assert exported.status_code == 403, exported.text


# Review S1: a client's exclusion list is the deal team's; nobody else learns the company is a client.
async def test_exclusion_list_is_for_the_client_deal_team_only(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.analyst)
    rival = await world.company("Rival Industries", "strategic_buyer")
    url = f"/api/v1/companies/{world.client_id}/exclusions"

    added = await world.partner.client.post(url, json={"company_id": rival}, headers=world.partner.headers)
    assert added.status_code == 201, added.text
    assert (await world.analyst.client.get(url, headers=world.analyst.headers)).status_code == 200
    by_analyst = await world.analyst.client.post(url, json={"company_id": rival}, headers=world.analyst.headers)
    assert by_analyst.status_code == 403, by_analyst.text

    for outsider in (world.outsider, world.admin):
        assert (await outsider.client.get(url, headers=outsider.headers)).status_code == 404
        refused = await outsider.client.post(url, json={"company_id": rival}, headers=outsider.headers)
        assert refused.status_code == 404
        removed = await outsider.client.delete(f"{url}/{rival}", headers=outsider.headers)
        assert removed.status_code == 404
    rows = (await world.partner.client.get(url, headers=world.partner.headers)).json()
    assert [row["company_id"] for row in rows] == [rival]


# Review S4 (ROLE-01 c2, AUTHZ-02 c8): staffing grants read whatever the role; edits still need the permission.
@pytest.mark.parametrize("persona", ["admin", "compliance"])
async def test_a_staffed_admin_or_compliance_user_reads_their_deal(world, persona):
    member = getattr(world, persona)
    mandate = await create_mandate(world, world.partner, world.client_id)
    url = f"/api/v1/mandates/{mandate['id']}"
    assert (await member.client.get(url, headers=member.headers)).status_code == 404
    await staff(world, mandate["id"], member)

    read = await member.client.get(url, headers=member.headers)
    assert read.status_code == 200, read.text
    assert read.json()["can_edit"] is False
    listed = (await member.client.get("/api/v1/mandates/", headers=member.headers)).json()
    assert "Falcon" in str(listed)
    edit = await member.client.patch(url, json={"version": read.json()["version"], "estimated_ev": "1"}, headers=member.headers)
    assert edit.status_code == 403, edit.text
