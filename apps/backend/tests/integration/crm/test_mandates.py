from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.modules.mandate.models import WallCrossing
from src.modules.mandate.stages import SELL_SIDE_STAGES
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate, mandate_payload

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.director = await built.actor("dirk", RoleName.DIRECTOR)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.client_id = await built.company("Acme Holding")
    built.target_id = await built.company("Widget Works")
    yield built
    await built.close()
    set_clock(SystemClock())


# DEAL-01 c1: code name, client, type, sector, lead partner and estimated EV are required; code name unique.
async def test_mandate_requires_its_fields_and_a_unique_code_name(world):
    partner = world.partner
    for missing in ("code_name", "client_id", "type", "sector_id", "lead_partner_id", "estimated_ev"):
        payload = mandate_payload(world, world.client_id, partner.id)
        del payload[missing]
        response = await partner.client.post("/api/v1/mandates/", json=payload, headers=partner.headers)
        assert response.status_code == 422, missing
        assert missing in [error["field"] for error in response.json()["errors"]]

    created = await create_mandate(world, partner, world.client_id)
    assert created["code_name"] == "Falcon"
    assert created["lead_partner_id"] == partner.id

    duplicate = await partner.client.post(
        "/api/v1/mandates/",
        json=mandate_payload(world, world.client_id, partner.id, code_name="falcon"),
        headers=partner.headers,
    )
    assert duplicate.status_code == 409


async def test_lead_partner_must_hold_the_partner_role(world):
    response = await world.partner.client.post(
        "/api/v1/mandates/",
        json=mandate_payload(world, world.client_id, world.analyst.id),
        headers=world.partner.headers,
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "lead_partner_id"


async def test_only_roles_with_mandates_create_can_create(world):
    response = await world.director.client.post(
        "/api/v1/mandates/",
        json=mandate_payload(world, world.client_id, world.partner.id),
        headers=world.director.headers,
    )
    assert response.status_code == 403


# DEAL-01 c3: the code name cannot contain the client or target name.
@pytest.mark.parametrize("code_name", ["Acme Falcon", "Project ACME HOLDING", "Widget-Works deal"])
async def test_code_name_cannot_contain_client_or_target_name(world, code_name):
    response = await world.partner.client.post(
        "/api/v1/mandates/",
        json=mandate_payload(world, world.client_id, world.partner.id, code_name=code_name, target_id=world.target_id),
        headers=world.partner.headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["field"] == "code_name"


async def test_renaming_to_a_name_containing_the_client_is_rejected(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    response = await world.partner.client.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": mandate["version"], "code_name": "Acme Two"},
        headers=world.partner.headers,
    )
    assert response.status_code == 422


# DEAL-01 c5 (derived): every mandate type uses the sell-side stage list.
@pytest.mark.parametrize("mandate_type", ["sell_side", "buy_side", "fundraising", "debt_advisory"])
async def test_every_mandate_type_uses_the_sell_side_stages(world, mandate_type):
    mandate = await create_mandate(world, world.partner, world.client_id, type=mandate_type)
    assert mandate["stages"] == [stage.value for stage in SELL_SIDE_STAGES]
    assert mandate["stage"] == SELL_SIDE_STAGES[0].value


# DEAL-03 c2: a stale write gets a conflict and the newer version.
async def test_stale_write_returns_conflict_with_the_newer_version(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await add_member(world, mandate["id"], world.analyst.id, "analyst")

    first = await world.partner.client.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": mandate["version"], "estimated_ev": "30000"},
        headers=world.partner.headers,
    )
    assert first.status_code == 200
    assert first.json()["version"] == mandate["version"] + 1

    second = await world.analyst.client.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": mandate["version"], "estimated_ev": "40000"},
        headers=world.analyst.headers,
    )
    assert second.status_code == 409
    body = second.json()["detail"]
    assert "changed" in body["message"]
    assert body["current"]["estimated_ev"] == "30000.00"
    assert body["current"]["version"] == first.json()["version"]

    reread = await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}", headers=world.partner.headers)
    assert reread.json()["estimated_ev"] == "30000.00"


# DEAL-03 c3: the history shows who, when, old and new value for every change.
async def test_history_shows_who_when_old_and_new(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    later = datetime(2026, 10, 11, 14, 30, tzinfo=UTC)
    set_clock(FrozenClock(later))
    await world.partner.client.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": mandate["version"], "estimated_ev": "30000", "code_name": "Heron"},
        headers=world.partner.headers,
    )

    history = (
        await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/history", headers=world.partner.headers)
    ).json()
    changes = {
        (entry["field"], entry["old_value"], entry["new_value"]) for entry in history if entry["at"].startswith("2026-10-11")
    }
    assert ("estimated_ev", "25000.00", "30000.00") in changes
    assert ("code_name", "Falcon", "Heron") in changes
    for entry in history:
        assert entry["user_name"] == "paula"
        assert entry["user_id"] == world.partner.id
    assert any(entry["action"] == "mandate.created" for entry in history)


async def add_member(world, mandate_id: int, user_id: int, role: str, actor=None, **extra):
    actor = actor or world.partner
    response = await actor.client.post(
        f"/api/v1/mandates/{mandate_id}/team",
        json={"user_id": user_id, "role": role, **extra},
        headers=actor.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# AUTHZ-02 c1: not on the team -> not in the list, not in search, and Not found by URL.
async def test_non_member_cannot_list_search_or_open_the_deal(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    outsider = world.outsider

    listed = await outsider.client.get("/api/v1/mandates/", headers=outsider.headers)
    assert listed.status_code == 200
    assert listed.json() == []
    searched = await outsider.client.get("/api/v1/mandates/?q=Falc", headers=outsider.headers)
    assert searched.json() == []
    opened = await outsider.client.get(f"/api/v1/mandates/{mandate['id']}", headers=outsider.headers)
    assert opened.status_code == 404
    missing = await outsider.client.get("/api/v1/mandates/999999", headers=outsider.headers)
    assert opened.json()["detail"] == missing.json()["detail"]

    own = await world.partner.client.get("/api/v1/mandates/?q=falc", headers=world.partner.headers)
    assert [item["code_name"] for item in own.json()] == ["Falcon"]


# ROLE-01 c2: an unstaffed Admin sees no deal content.
async def test_unstaffed_admin_sees_no_deal(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    admin = world.admin
    assert (await admin.client.get("/api/v1/mandates/", headers=admin.headers)).json() == []
    assert (await admin.client.get(f"/api/v1/mandates/{mandate['id']}", headers=admin.headers)).status_code == 404
    assert (await admin.client.get(f"/api/v1/mandates/{mandate['id']}/history", headers=admin.headers)).status_code == 404


# AUTHZ-03 c1: an added user gets access immediately and is notified, in-app and by email.
@pytest.mark.parametrize("assigner", ["partner", "director"])
async def test_added_member_gets_access_and_is_notified(world, assigner):
    mandate = await create_mandate(world, world.partner, world.client_id)
    if assigner == "director":
        await add_member(world, mandate["id"], world.director.id, "director")
    actor = getattr(world, assigner)
    await add_member(world, mandate["id"], world.analyst.id, "analyst", actor=actor)

    opened = await world.analyst.client.get(f"/api/v1/mandates/{mandate['id']}", headers=world.analyst.headers)
    assert opened.status_code == 200

    notifications = (await world.analyst.client.get("/api/v1/notifications/", headers=world.analyst.headers)).json()
    assert [(n["kind"], n["link"]) for n in notifications] == [("deal_team.added", f"/deals/{mandate['id']}")]
    assert "Falcon" in notifications[0]["title"]
    sent = [email for email in world.emails.sent if email.to == world.analyst.email]
    assert len(sent) == 1
    assert "Falcon" in sent[0].subject
    assert "Acme" not in sent[0].subject + sent[0].body


# AUTHZ-03 c2: a removed user loses access at their next request; what they did stays attributed.
async def test_removed_member_loses_access_and_keeps_attribution(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await add_member(world, mandate["id"], world.analyst.id, "analyst")
    edited = await world.analyst.client.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": mandate["version"], "estimated_ev": "26000"},
        headers=world.analyst.headers,
    )
    assert edited.status_code == 200

    removed = await world.partner.client.delete(
        f"/api/v1/mandates/{mandate['id']}/team/{world.analyst.id}", headers=world.partner.headers
    )
    assert removed.status_code == 204

    assert (
        await world.analyst.client.get(f"/api/v1/mandates/{mandate['id']}", headers=world.analyst.headers)
    ).status_code == 404
    assert (await world.analyst.client.get("/api/v1/mandates/", headers=world.analyst.headers)).json() == []
    history = (
        await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/history", headers=world.partner.headers)
    ).json()
    assert any(entry["user_id"] == world.analyst.id and entry["user_name"] == "anna" for entry in history)


# AUTHZ-03 c3: an analyst cannot add someone.
async def test_analyst_cannot_add_team_members(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await add_member(world, mandate["id"], world.analyst.id, "analyst")
    team = (await world.analyst.client.get(f"/api/v1/mandates/{mandate['id']}/team", headers=world.analyst.headers)).json()
    assert team["can_manage"] is False
    response = await world.analyst.client.post(
        f"/api/v1/mandates/{mandate['id']}/team",
        json={"user_id": world.director.id, "role": "director"},
        headers=world.analyst.headers,
    )
    assert response.status_code == 403
    partner_view = (
        await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/team", headers=world.partner.headers)
    ).json()
    assert partner_view["can_manage"] is True


# AUTHZ-03 c4: removing the last lead partner is blocked.
async def test_last_lead_partner_cannot_be_removed(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    response = await world.partner.client.delete(
        f"/api/v1/mandates/{mandate['id']}/team/{world.partner.id}", headers=world.partner.headers
    )
    assert response.status_code == 409
    assert "lead partner" in response.json()["detail"]
    team = (await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/team", headers=world.partner.headers)).json()
    assert [member["user_id"] for member in team["members"]] == [world.partner.id]


# AUTHZ-03 c5: every team change lands in the wall-crossing register with who, when and by whom.
async def test_team_changes_land_in_the_wall_crossing_register(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await add_member(world, mandate["id"], world.analyst.id, "analyst", expires_at="2026-12-31T00:00:00Z")
    await world.partner.client.delete(
        f"/api/v1/mandates/{mandate['id']}/team/{world.analyst.id}", headers=world.partner.headers
    )

    rows = (await world.db.execute(select(WallCrossing).where(WallCrossing.mandate_id == mandate["id"]))).scalars().all()
    assert [(row.action, row.user_id, row.by_user_id, row.at) for row in rows] == [
        ("added", world.partner.id, world.partner.id, NOW),
        ("added", world.analyst.id, world.partner.id, NOW),
        ("removed", world.analyst.id, world.partner.id, NOW),
    ]
    register = (
        await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/wall-crossings", headers=world.partner.headers)
    ).json()
    assert [(entry["action"], entry["user_name"], entry["by_user_name"]) for entry in register] == [
        ("added", "paula", "paula"),
        ("added", "anna", "paula"),
        ("removed", "anna", "paula"),
    ]


async def test_membership_expiry_ends_access(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await add_member(world, mandate["id"], world.analyst.id, "analyst", expires_at="2026-10-12T00:00:00Z")
    assert (
        await world.analyst.client.get(f"/api/v1/mandates/{mandate['id']}", headers=world.analyst.headers)
    ).status_code == 200
    set_clock(FrozenClock(datetime(2026, 10, 13, tzinfo=UTC)))
    assert (
        await world.analyst.client.get(f"/api/v1/mandates/{mandate['id']}", headers=world.analyst.headers)
    ).status_code == 404


# DEAL-07 c1 + c2: https links with a label, stored not uploaded, visible to the team only.
async def test_document_links_are_labelled_https_and_team_only(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    url = f"/api/v1/mandates/{mandate['id']}/links"
    created = await world.partner.client.post(
        url, json={"label": "VDR", "url": "https://vdr.example.com/rooms/falcon"}, headers=world.partner.headers
    )
    assert created.status_code == 201
    assert created.json()["label"] == "VDR"

    for bad in (
        {"label": "IM", "url": "http://files.example.com/im.pdf"},
        {"label": "IM", "url": "javascript:alert(1)"},
        {"label": "", "url": "https://files.example.com/im.pdf"},
        {"url": "https://files.example.com/im.pdf"},
    ):
        assert (await world.partner.client.post(url, json=bad, headers=world.partner.headers)).status_code == 422

    links = (await world.partner.client.get(url, headers=world.partner.headers)).json()
    assert [(link["label"], link["url"]) for link in links] == [("VDR", "https://vdr.example.com/rooms/falcon")]
    assert (await world.outsider.client.get(url, headers=world.outsider.headers)).status_code == 404

    compliance = await world.actor("cora", RoleName.COMPLIANCE)
    assert (await compliance.client.get(url, headers=compliance.headers)).status_code == 404


# A quote in the code name cannot break the CSV download header.
async def test_export_filename_survives_a_quote_in_the_code_name(world):
    mandate = await create_mandate(world, world.partner, world.client_id, code_name='Pro"ject Zeta')

    response = await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/export", headers=world.partner.headers)

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.count('"') == 2
    assert "filename*=UTF-8''Pro%22ject%20Zeta.csv" in disposition
