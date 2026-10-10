"""Chinese-wall fixes from the feat/ma-crm review."""

from datetime import UTC, datetime

import pytest

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

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
