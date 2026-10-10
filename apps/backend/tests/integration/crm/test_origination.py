"""Ticket #12: origination pipeline (ORI-01), pitches, credentials (ORI-02), outcomes (ORI-03), dormant prospects (ORI-04)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.jobs import job_runner
from src.modules.notification.service import NotificationService
from src.modules.origination.jobs import ORIGINATION_JOB, run_origination_jobs
from src.modules.role.permissions import RoleName
from src.modules.task.models import Task
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
BASE = "/api/v1/origination"


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.colleague = await built.actor("dirk", RoleName.DIRECTOR)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.compliance = await built.actor("cora", RoleName.COMPLIANCE)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.company_id = await built.company("Acme Holding")
    yield built
    await built.close()
    set_clock(SystemClock())


async def get(actor, path: str):
    return await actor.client.get(path, headers=actor.headers)


async def post(actor, path: str, body: dict):
    return await actor.client.post(path, json=body, headers=actor.headers)


async def opportunity(world, actor=None, **overrides) -> dict:
    actor = actor or world.partner
    body = {
        "company_id": world.company_id,
        "type": "sell_side",
        "trigger": "succession",
        "estimated_ev": "40000",
        "probability": 30,
        "sector_id": world.sector_id,
        **overrides,
    }
    response = await post(actor, f"{BASE}/opportunities", body)
    assert response.status_code == 201, response.text
    return response.json()


async def move(world, opportunity_id: int, stage: str, actor=None, **body):
    return await post(actor or world.partner, f"{BASE}/opportunities/{opportunity_id}/stage", {"stage": stage, **body})


async def invite(world, opportunity_id: int, actor) -> None:
    response = await post(world.partner, f"{BASE}/opportunities/{opportunity_id}/members", {"user_id": actor.id})
    assert response.status_code == 201, response.text


async def run_jobs(world, now: datetime) -> None:
    await run_origination_jobs(world.db, now, NotificationService(world.emails))


async def tasks_of(world, user_id: int) -> list[Task]:
    world.db.expire_all()
    return list((await world.db.execute(select(Task).where(Task.assignee_id == user_id))).scalars())


# ORI-01 c1: type, trigger, estimated EV and probability; it appears in the origination pipeline.
async def test_created_opportunity_appears_in_the_pipeline(world):
    created = await opportunity(world, type="debt_advisory", trigger="carve_out", probability=55)
    assert created["stage"] == "lead"
    assert (created["type"], created["trigger"], created["probability"]) == ("debt_advisory", "carve_out", 55)
    assert created["estimated_ev"] == "40000.00"
    pipeline = (await get(world.partner, f"{BASE}/opportunities")).json()
    assert [row["id"] for row in pipeline] == [created["id"]]
    assert pipeline[0]["company_name"] == "Acme Holding"
    bad = await post(world.partner, f"{BASE}/opportunities", {**created, "company_id": world.company_id, "trigger": "boredom"})
    assert bad.status_code == 422
    over = await post(
        world.partner,
        f"{BASE}/opportunities",
        {"company_id": world.company_id, "type": "sell_side", "trigger": "growth", "estimated_ev": "1", "probability": 101},
    )
    assert over.status_code == 422


# ORI-01 c2: the eight stages.
async def test_stages_are_the_eight_origination_stages(world):
    stages = (await get(world.partner, f"{BASE}/stages")).json()
    assert stages == ["lead", "contacted", "meeting_held", "pitch", "engagement_letter_sent", "won", "lost", "on_hold"]
    created = await opportunity(world)
    for stage in ("contacted", "meeting_held", "pitch", "engagement_letter_sent"):
        response = await move(world, created["id"], stage)
        assert response.status_code == 200, response.text
        assert response.json()["stage"] == stage
    assert (await move(world, created["id"], "signed")).status_code == 422


# ORI-01 c3: visible only to its owner and invited colleagues (same wall logic as deals).
async def test_opportunity_is_visible_only_to_owner_and_invited_colleagues(world):
    created = await opportunity(world)
    path = f"{BASE}/opportunities/{created['id']}"
    for stranger in (world.outsider, world.colleague, world.compliance, world.admin):
        assert (await get(stranger, path)).status_code == 404
        assert (await get(stranger, f"{BASE}/opportunities")).json() == []
    candidates = {row["user_id"] for row in (await get(world.partner, f"{path}/candidates")).json()}
    assert world.colleague.id in candidates
    assert world.admin.id not in candidates
    await invite(world, created["id"], world.colleague)
    assert (await get(world.colleague, path)).status_code == 200
    assert [row["id"] for row in (await get(world.colleague, f"{BASE}/opportunities")).json()] == [created["id"]]
    # An invitee works on it but does not invite others; a stranger cannot even find it.
    assert (await post(world.colleague, f"{path}/members", {"user_id": world.analyst.id})).status_code == 403
    assert (await post(world.outsider, f"{path}/members", {"user_id": world.outsider.id})).status_code == 404
    # Same wall as deals: a role without deals.read_staffed sees nothing even when invited.
    await invite(world, created["id"], world.admin)
    assert (await get(world.admin, path)).status_code == 404
    removed = await world.partner.client.delete(f"{path}/members/{world.colleague.id}", headers=world.partner.headers)
    assert removed.status_code == 204
    assert (await get(world.colleague, path)).status_code == 404


# ORI-01 c4: a company with an active mandate shows a conflict warning.
async def test_company_with_an_active_mandate_shows_a_conflict_warning(world):
    clean = await opportunity(world)
    assert clean["conflict_warning"] is False
    seller = await world.company("Northwind Trading")
    await create_mandate(world, world.outsider, seller, code_name="Heron", target_id=world.company_id)
    warned = await opportunity(world)
    assert warned["conflict_warning"] is True
    # The warning names no deal: the partner is not on Heron's team.
    assert "Heron" not in str(warned)
    preview = (await get(world.partner, f"{BASE}/conflict-warning?company_id={world.company_id}")).json()
    assert preview == {"conflict_warning": True}


# ORI-02 c1: pitch deck links and past deals as credentials are listed on the opportunity.
async def test_pitch_deck_links_and_credentials_are_listed(world):
    created = await opportunity(world)
    path = f"{BASE}/opportunities/{created['id']}"
    tombstone = await closed_deal(world, "Kestrel", tombstone=True)
    link = await post(world.partner, f"{path}/links", {"label": "Pitch deck", "url": "https://files.firm.be/pitch.pptx"})
    assert link.status_code == 201, link.text
    assert (await post(world.partner, f"{path}/links", {"label": "Deck", "url": "http://insecure"})).status_code == 422
    credential = await post(world.partner, f"{path}/credentials", {"mandate_id": tombstone})
    assert credential.status_code == 201, credential.text
    detail = (await get(world.partner, path)).json()
    assert [(row["label"], row["url"]) for row in detail["links"]] == [("Pitch deck", "https://files.firm.be/pitch.pptx")]
    assert [row["code_name"] for row in detail["credentials"]] == ["Kestrel"]


async def closed_deal(world, code_name: str, tombstone: bool, ev: str = "30000", sector_id: int | None = None) -> int:
    client_id = await world.company(f"Seller {len(code_name)}{code_name[::-1]} Corp")
    mandate = await create_mandate(
        world, world.outsider, client_id, code_name=code_name, sector_id=sector_id or world.sector_id
    )
    response = await post(
        world.outsider,
        f"/api/v1/mandates/{mandate['id']}/close",
        {
            "version": mandate["version"],
            "outcome": "closed_won",
            "final_ev": ev,
            "buyer": "Some Buyer",
            "ev_ebitda": "8",
            "closing_date": "2026-01-15",
            "tombstone_allowed": tombstone,
        },
    )
    assert response.status_code == 200, response.text
    return mandate["id"]


# ORI-02 c2: credential search by sector and size shows only closed deals marked public.
async def test_credential_search_shows_only_public_closed_deals(world):
    other_sector = (
        await post(world.admin, "/api/v1/picklists/", {"kind": "sector", "code": "health", "label_en": "Healthcare"})
    ).json()["id"]
    public = await closed_deal(world, "Kestrel", tombstone=True, ev="30000")
    await closed_deal(world, "Plover", tombstone=False, ev="30000")
    await closed_deal(world, "Osprey", tombstone=True, ev="900000")
    await closed_deal(world, "Egret", tombstone=True, ev="30000", sector_id=other_sector)
    running = await world.company("Running Ltd")
    await create_mandate(world, world.outsider, running, code_name="Gannet")
    found = (await get(world.partner, f"{BASE}/credentials?sector_id={world.sector_id}&ev_min=10000&ev_max=50000")).json()
    assert [row["id"] for row in found] == [public]
    assert found[0]["code_name"] == "Kestrel"
    everything = {row["code_name"] for row in (await get(world.partner, f"{BASE}/credentials")).json()}
    assert everything == {"Kestrel", "Osprey", "Egret"}
    created = await opportunity(world)
    private = await closed_deal(world, "Curlew", tombstone=False)
    refused = await post(world.partner, f"{BASE}/opportunities/{created['id']}/credentials", {"mandate_id": private})
    assert refused.status_code == 422


# ORI-03 c1: Won creates a mandate with company, team and fee draft copied, and it goes to conflict check.
async def test_won_creates_a_mandate_with_company_team_and_fee_draft_and_runs_the_conflict_check(world):
    created = await opportunity(world)
    path = f"{BASE}/opportunities/{created['id']}"
    await invite(world, created["id"], world.colleague)
    await invite(world, created["id"], world.analyst)
    draft = await world.partner.client.put(
        f"{path}/fee-draft",
        json={
            "retainer_monthly": "15000",
            "success_fee_kind": "percent",
            "success_fee_percent": "2.5",
            "minimum_fee": "300000",
        },
        headers=world.partner.headers,
    )
    assert draft.status_code == 200, draft.text
    assert (await post(world.colleague, f"{path}/win", {"code_name": "Falcon"})).status_code == 403
    won = await post(world.partner, f"{path}/win", {"code_name": "Falcon"})
    assert won.status_code == 201, won.text
    mandate_id = won.json()["mandate_id"]
    assert won.json()["stage"] == "won"

    mandate = (await get(world.partner, f"/api/v1/mandates/{mandate_id}")).json()
    assert (mandate["client_id"], mandate["type"], mandate["estimated_ev"]) == (world.company_id, "sell_side", "40000.00")
    assert mandate["conflict_status"] == "clear"
    team = (await get(world.partner, f"/api/v1/mandates/{mandate_id}/team")).json()
    roles = {member["user_id"]: member["role"] for member in team["members"]}
    assert roles == {world.partner.id: "lead_partner", world.colleague.id: "director", world.analyst.id: "analyst"}
    fees = (await get(world.partner, f"/api/v1/mandates/{mandate_id}/fees")).json()
    assert (fees["retainer_monthly"], fees["success_fee_percent"], fees["minimum_fee"]) == ("15000.00", "2.500", "300000.00")
    assert (await post(world.partner, f"{path}/win", {"code_name": "Falcon Two"})).status_code == 409

    # A hit sends the new mandate to conflict review (AUTHZ-05).
    seller = await world.company("Northwind Trading")
    await create_mandate(world, world.outsider, seller, code_name="Heron", target_id=world.company_id)
    second = await opportunity(world)
    hit = await post(world.partner, f"{BASE}/opportunities/{second['id']}/win", {"code_name": "Swift"})
    assert hit.status_code == 201, hit.text
    reviewed = (await get(world.partner, f"/api/v1/mandates/{hit.json()['mandate_id']}")).json()
    assert (reviewed["conflict_status"], reviewed["stage"]) == ("review", "conflict_review")


async def test_fee_draft_is_hidden_without_fees_read(world):
    created = await opportunity(world)
    await invite(world, created["id"], world.colleague)
    path = f"{BASE}/opportunities/{created['id']}"
    assert "fee_draft" not in (await get(world.colleague, path)).json()
    assert "fee_draft" in (await get(world.partner, path)).json()
    refused = await world.colleague.client.put(
        f"{path}/fee-draft", json={"success_fee_kind": "fixed", "success_fee_fixed": "1"}, headers=world.colleague.headers
    )
    assert refused.status_code == 403


# ORI-03 c2: Lost needs a reason (fee, competitor, timing, client decided not to sell); competitor advisor optional.
async def test_lost_requires_a_reason_and_takes_an_optional_competitor(world):
    created = await opportunity(world)
    missing = await move(world, created["id"], "lost")
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["field"] == "lost_reason"
    assert (await move(world, created["id"], "lost", lost_reason="bad_luck")).status_code == 422
    lost = await move(world, created["id"], "lost", lost_reason="client_decided_not_to_sell")
    assert lost.status_code == 200, lost.text
    assert (lost.json()["lost_reason"], lost.json()["competitor_advisor"]) == ("client_decided_not_to_sell", None)
    other = await opportunity(world)
    beaten = await move(world, other["id"], "lost", lost_reason="competitor", competitor_advisor="Big Four Corporate Finance")
    assert beaten.json()["competitor_advisor"] == "Big Four Corporate Finance"
    for reason in ("fee", "timing"):
        third = await opportunity(world)
        assert (await move(world, third["id"], "lost", lost_reason=reason)).status_code == 200


# ORI-03 c3: On hold, when the revisit date arrives, the owner gets a task.
async def test_on_hold_creates_an_owner_task_when_the_revisit_date_arrives(world):
    created = await opportunity(world)
    await invite(world, created["id"], world.colleague)
    assert (await move(world, created["id"], "on_hold")).status_code == 422
    held = await move(world, created["id"], "on_hold", actor=world.colleague, revisit_date="2026-11-02")
    assert held.status_code == 200, held.text
    await run_jobs(world, datetime(2026, 11, 1, 9, 0, tzinfo=UTC))
    assert await tasks_of(world, world.partner.id) == []
    await run_jobs(world, datetime(2026, 11, 2, 7, 0, tzinfo=UTC))
    await run_jobs(world, datetime(2026, 11, 2, 8, 0, tzinfo=UTC))
    tasks = await tasks_of(world, world.partner.id)
    assert len(tasks) == 1
    assert tasks[0].due_date.isoformat() == "2026-11-02"
    assert "Acme Holding" in tasks[0].title
    assert await tasks_of(world, world.colleague.id) == []
    assert ORIGINATION_JOB in job_runner.names


# ORI-04: no activity on a prospect for 90 days (configurable) tasks the relationship holder.
async def test_dormant_prospect_tasks_the_relationship_holder(world):
    created = await opportunity(world)
    await run_jobs(world, NOW + timedelta(days=89))
    assert await tasks_of(world, world.partner.id) == []
    await run_jobs(world, NOW + timedelta(days=90))
    await run_jobs(world, NOW + timedelta(days=91))
    tasks = await tasks_of(world, world.partner.id)
    assert len(tasks) == 1
    assert "Reconnect" in tasks[0].title

    # An activity on the company resets the clock.
    set_clock(FrozenClock(NOW + timedelta(days=100)))
    logged = await post(
        world.partner,
        "/api/v1/activities/",
        {
            "type": "call",
            "occurred_at": (NOW + timedelta(days=100)).isoformat(),
            "note": "Catch-up",
            "links": [{"record_type": "company", "record_id": world.company_id}],
        },
    )
    assert logged.status_code == 201, logged.text
    await run_jobs(world, NOW + timedelta(days=150))
    assert len(await tasks_of(world, world.partner.id)) == 1

    # Configurable threshold (settings.manage).
    assert (
        await world.partner.client.put(f"{BASE}/settings", json={"dormant_days": 30}, headers=world.partner.headers)
    ).status_code == 403
    saved = await world.admin.client.put(f"{BASE}/settings", json={"dormant_days": 30}, headers=world.admin.headers)
    assert saved.status_code == 200
    assert saved.json()["dormant_days"] == 30
    await run_jobs(world, NOW + timedelta(days=131))
    assert len(await tasks_of(world, world.partner.id)) == 2

    # Closed opportunities are no longer prospects.
    await move(world, created["id"], "lost", lost_reason="timing")
    await run_jobs(world, NOW + timedelta(days=400))
    assert len(await tasks_of(world, world.partner.id)) == 2
