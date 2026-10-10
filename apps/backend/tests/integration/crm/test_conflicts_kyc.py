"""Ticket #9: conflict check on new mandates (AUTHZ-05, DEAL-01 c2/c4) and the KYC / engagement letter gate (ORI-05)."""

from datetime import UTC, datetime, timedelta

import pytest

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.jobs import job_runner
from src.modules.compliance.jobs import COMPLIANCE_JOB, run_compliance_jobs
from src.modules.notification.service import NotificationService
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate, mandate_payload

pytestmark = pytest.mark.asyncio

# A Friday, so working-day arithmetic crosses a weekend.
NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
KYC_DONE = {"ubo_check": True, "id_check": True, "pep_sanctions_screening": True, "sanctions_hit": False}


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.other = await built.actor("peter", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.compliance = await built.actor("cora", RoleName.COMPLIANCE)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.client_id = await built.company("Acme Holding")
    built.target_id = await built.company("Widget Works")
    yield built
    await built.close()
    set_clock(SystemClock())


async def get(actor, path: str):
    return await actor.client.get(path, headers=actor.headers)


async def post(actor, path: str, body: dict):
    return await actor.client.post(path, json=body, headers=actor.headers)


async def company(world, name: str, parent_id: int | None = None) -> int:
    response = await post(
        world.partner,
        "/api/v1/companies/",
        {
            "name": name,
            "type": "target",
            "country_id": world.country_id,
            "vat_or_registry_number": f"{name}-{parent_id}",
            "ignore_similar": True,
            "parent_id": parent_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def staff(world, mandate_id: int, actor, role: str = "analyst", by=None) -> None:
    by = by or world.partner
    response = await post(by, f"/api/v1/mandates/{mandate_id}/team", {"user_id": actor.id, "role": role})
    assert response.status_code == 201, response.text


async def existing_deal(world) -> dict:
    """An active mandate by another partner, selling Northwind with Acme as its target: Acme is on the other side."""
    seller = await company(world, "Northwind Trading")
    return await create_mandate(world, world.other, seller, code_name="Heron", target_id=world.client_id)


async def conflicts(world, mandate_id: int):
    return await get(world.compliance, f"/api/v1/mandates/{mandate_id}/conflicts")


async def decide(actor, mandate_id: int, decision: str, reason: str | None = "Different teams, no overlap"):
    return await post(actor, f"/api/v1/mandates/{mandate_id}/conflicts/decision", {"decision": decision, "reason": reason})


# AUTHZ-05 c1: client, target and counterparties, with their group entities, are checked against active deals.
async def test_client_target_and_counterparties_with_groups_are_checked_against_active_deals(world):
    parent = await company(world, "Orion Industries")
    subsidiary = await company(world, "Lumen Labs", parent_id=parent)
    counterparty = await company(world, "Quasar Capital")
    await create_mandate(world, world.other, parent, code_name="Heron")
    await create_mandate(world, world.other, counterparty, code_name="Kite")
    clean = await create_mandate(world, world.partner, world.client_id, code_name="Swift")
    assert clean["conflict_status"] == "clear"

    mandate = await create_mandate(
        world, world.partner, world.target_id, code_name="Falcon", target_id=subsidiary, counterparty_ids=[counterparty]
    )

    assert mandate["conflict_status"] == "review"
    assert mandate["stage"] == "conflict_review"
    hits = (await conflicts(world, mandate["id"])).json()
    assert sorted(hit["other_code_name"] for hit in hits) == ["Heron", "Kite"]
    assert {hit["company_name"] for hit in hits} == {"Lumen Labs", "Quasar Capital"}


# AUTHZ-05 c1: closed or aborted deals count for 24 months, then drop out.
async def test_closed_deals_count_for_24_months(world):
    old = await existing_deal(world)
    closed = await post(
        world.other,
        f"/api/v1/mandates/{old['id']}/close",
        {"version": old["version"], "outcome": "aborted", "abort_reason": "Seller withdrew"},
    )
    assert closed.status_code == 200, closed.text

    set_clock(FrozenClock(NOW + timedelta(days=700)))
    recent = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    assert recent["conflict_status"] == "review"

    assert (await decide(world.compliance, recent["id"], "reject")).status_code == 200

    set_clock(FrozenClock(NOW + timedelta(days=740)))
    stale = await create_mandate(world, world.partner, world.client_id, code_name="Osprey")
    assert stale["conflict_status"] == "clear"


# AUTHZ-05 c2 + DEAL-01 c4: a hit keeps the deal in Conflict review, invisible to all but compliance and the creator;
# only compliance sees what it conflicts with.
async def test_a_conflict_hides_the_deal_from_everyone_but_compliance_and_the_creator(world):
    await existing_deal(world)
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    await staff(world, mandate["id"], world.analyst)
    mid = mandate["id"]

    for outsider in (world.analyst, world.other, world.admin):
        assert (await get(outsider, f"/api/v1/mandates/{mid}")).status_code == 404
        listed = await get(outsider, "/api/v1/mandates/?q=falcon")
        assert "Falcon" not in listed.text

    mine = await get(world.partner, "/api/v1/mandates/?q=falcon")
    assert [deal["code_name"] for deal in mine.json()] == ["Falcon"]
    assert (await get(world.partner, f"/api/v1/mandates/{mid}")).json()["conflict_status"] == "review"
    assert (await get(world.partner, f"/api/v1/mandates/{mid}/conflicts")).status_code == 403
    assert "Heron" not in (await get(world.partner, f"/api/v1/mandates/{mid}")).text

    listed = await get(world.compliance, "/api/v1/mandates/?q=falcon")
    assert [deal["code_name"] for deal in listed.json()] == ["Falcon"]
    reviews = (await get(world.compliance, "/api/v1/conflict-reviews/")).json()
    assert [review["code_name"] for review in reviews] == ["Falcon"]
    assert [hit["other_code_name"] for hit in (await conflicts(world, mid)).json()] == ["Heron"]


# AUTHZ-05 c2: the deal cannot leave Conflict review until compliance clears it.
async def test_the_deal_stays_in_conflict_review_until_cleared(world):
    await existing_deal(world)
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")

    blocked = await post(
        world.partner, f"/api/v1/mandates/{mandate['id']}/stage", {"version": mandate["version"], "stage": "preparation"}
    )

    assert blocked.status_code == 422
    assert blocked.json()["detail"]["reasons"] == ["Compliance must clear the conflict check."]


# AUTHZ-05 c3: clear or reject logs decision, reason and approver; the deal becomes Active or Rejected.
async def test_compliance_clears_or_rejects_with_a_logged_reason(world):
    await existing_deal(world)
    cleared = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    rejected = await create_mandate(world, world.partner, world.client_id, code_name="Osprey")
    await staff(world, cleared["id"], world.analyst)

    assert (await decide(world.partner, cleared["id"], "clear")).status_code == 403
    assert (await decide(world.compliance, cleared["id"], "clear", reason=" ")).status_code == 422
    response = await decide(world.compliance, cleared["id"], "clear")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conflict_status"] == "cleared"
    assert body["decided_by_name"] == "cora"
    assert body["reason"] == "Different teams, no overlap"
    reread = await get(world.analyst, f"/api/v1/mandates/{cleared['id']}")
    assert reread.status_code == 200
    assert reread.json()["stage"] == "preparation"

    rejection = await decide(world.compliance, rejected["id"], "reject", reason="We act for the buyer")
    assert rejection.status_code == 200
    deal = (await get(world.partner, f"/api/v1/mandates/{rejected['id']}")).json()
    assert deal["conflict_status"] == "rejected"
    assert deal["stage"] == "aborted"
    assert deal["closed_at"] is not None

    audit = (await get(world.compliance, "/api/v1/audit/?record_type=mandate")).json()["data"]
    decisions = {(row["action"], row["user_id"], (row["new_values"] or {}).get("reason")) for row in audit}
    assert ("conflict.cleared", world.compliance.id, "Different teams, no overlap") in decisions
    assert ("conflict.rejected", world.compliance.id, "We act for the buyer") in decisions


# AUTHZ-05 c4: names differing only by legal form or accents are still flagged.
@pytest.mark.parametrize(
    ("existing", "new"), [("Brasserie Dupont NV", "Brasserie Dupont SA"), ("Société Générale", "Societe Generale BV")]
)
async def test_legal_form_and_accents_do_not_hide_a_conflict(world, existing, new):
    first = await company(world, existing)
    second = await company(world, new)
    seller = await company(world, "Northwind Trading")
    await create_mandate(world, world.other, seller, code_name="Heron", target_id=first)

    mandate = await create_mandate(world, world.partner, second, code_name="Falcon")

    assert mandate["conflict_status"] == "review"
    hit = (await conflicts(world, mandate["id"])).json()[0]
    assert (hit["company_name"], hit["matched_company_name"]) == (new, existing)


async def test_unrelated_names_are_not_flagged(world):
    await existing_deal(world)
    mandate = await create_mandate(world, world.partner, world.target_id, code_name="Falcon")
    assert mandate["conflict_status"] == "clear"


# AUTHZ-05 (decision 16): the same company as client of two mandates is a repeat client, not two sides.
async def test_a_repeat_client_is_not_a_conflict(world):
    await create_mandate(world, world.other, world.client_id, code_name="Heron")
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    assert mandate["conflict_status"] == "clear"


# AUTHZ-05 c5: after 5 working days undecided, the lead partner and compliance are reminded, once.
async def test_undecided_review_reminds_lead_partner_and_compliance_after_5_working_days(world):
    await existing_deal(world)
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    notifications = NotificationService(world.emails)

    # Friday + 5 working days = the next Friday; the Thursday before is too early.
    await run_compliance_jobs(world.db, NOW + timedelta(days=6), notifications)
    assert world.emails.sent == []

    await run_compliance_jobs(world.db, NOW + timedelta(days=7), notifications)
    await run_compliance_jobs(world.db, NOW + timedelta(days=8), notifications)

    reminders = [email for email in world.emails.sent if "conflict review" in email.subject.lower()]
    assert sorted(email.to for email in reminders) == sorted([world.partner.email, world.compliance.email])
    for email in reminders:
        assert "Falcon" in email.subject
        assert "Acme" not in email.subject + email.body
    assert COMPLIANCE_JOB in job_runner.names
    assert mandate["id"]


# AUTHZ-05 c6: a counterparty added later re-runs the check for that party.
async def test_adding_a_counterparty_later_reruns_the_check(world):
    mandate = await create_mandate(world, world.partner, world.target_id, code_name="Falcon")
    await staff(world, mandate["id"], world.analyst)
    started = await post(
        world.partner, f"/api/v1/mandates/{mandate['id']}/stage", {"version": mandate["version"], "stage": "preparation"}
    )
    assert started.status_code == 200, started.text
    harmless = await company(world, "Nebula Partners")
    flagged = await company(world, "Quasar Capital")
    await create_mandate(world, world.other, flagged, code_name="Kite")

    ok = await post(world.partner, f"/api/v1/mandates/{mandate['id']}/counterparties", {"company_id": harmless})
    assert ok.status_code == 201, ok.text
    assert (await get(world.partner, f"/api/v1/mandates/{mandate['id']}")).json()["conflict_status"] == "clear"

    hit = await post(world.analyst, f"/api/v1/mandates/{mandate['id']}/counterparties", {"company_id": flagged})
    assert hit.status_code == 201, hit.text
    assert hit.json()["conflict_status"] == "review"
    found = (await conflicts(world, mandate["id"])).json()
    assert [(h["company_name"], h["other_code_name"]) for h in found] == [("Quasar Capital", "Kite")]
    names = [c["name"] for c in (await get(world.partner, f"/api/v1/mandates/{mandate['id']}/counterparties")).json()]
    assert names == ["Nebula Partners", "Quasar Capital"]
    # A running deal stays with its team while compliance reviews the new party, but cannot move on.
    deal = await get(world.analyst, f"/api/v1/mandates/{mandate['id']}")
    assert deal.status_code == 200
    blocked = await post(
        world.analyst, f"/api/v1/mandates/{mandate['id']}/stage", {"version": deal.json()["version"], "stage": "marketing"}
    )
    assert "Compliance must clear the conflict check." in blocked.json()["detail"]["reasons"]


# DEAL-01 c2: creation runs the check and puts the creator on the deal team.
async def test_creation_runs_the_check_and_staffs_the_creator(world):
    response = await post(
        world.partner, "/api/v1/mandates/", mandate_payload(world, world.client_id, world.other.id, code_name="Falcon")
    )
    assert response.status_code == 201, response.text
    mandate = response.json()
    assert mandate["conflict_status"] == "clear"
    team = (await get(world.partner, f"/api/v1/mandates/{mandate['id']}/team")).json()["members"]
    assert {member["user_id"] for member in team} == {world.partner.id, world.other.id}


# ORI-05 c1: without the engagement letter link or approved KYC the deal cannot pass Preparation.
async def test_engagement_letter_and_approved_kyc_gate_preparation(world):
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    mid = mandate["id"]
    deal = await get(world.partner, f"/api/v1/mandates/{mid}")
    await post(world.partner, f"/api/v1/mandates/{mid}/stage", {"version": deal.json()["version"], "stage": "preparation"})

    async def to_marketing():
        version = (await get(world.partner, f"/api/v1/mandates/{mid}")).json()["version"]
        return await post(world.partner, f"/api/v1/mandates/{mid}/stage", {"version": version, "stage": "marketing"})

    await post(
        world.partner,
        f"/api/v1/mandates/{mid}/links",
        {"label": "Engagement letter", "url": "https://files.example.com/el.pdf"},
    )
    blocked = await to_marketing()
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["reasons"] == ["KYC must be approved."]

    assert (await post(world.compliance, f"/api/v1/mandates/{mid}/kyc", KYC_DONE)).status_code == 200
    assert (await to_marketing()).status_code == 200


async def test_kyc_alone_does_not_pass_without_the_engagement_letter(world):
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    mid = mandate["id"]
    await post(world.compliance, f"/api/v1/mandates/{mid}/kyc", KYC_DONE)
    deal = (await get(world.partner, f"/api/v1/mandates/{mid}")).json()
    blocked = await post(world.partner, f"/api/v1/mandates/{mid}/stage", {"version": deal["version"], "stage": "marketing"})
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["reasons"] == [
        "Add the signed engagement letter as a document link labelled “Engagement letter”."
    ]


# ORI-05 c2: UBO, ID and PEP/sanctions checks make KYC Approved, with date and reviewer.
async def test_recording_all_three_checks_approves_kyc_with_date_and_reviewer(world):
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    path = f"/api/v1/mandates/{mandate['id']}/kyc"

    assert (await post(world.partner, path, KYC_DONE)).status_code == 403
    partial = await post(world.compliance, path, {**KYC_DONE, "id_check": False})
    assert partial.json()["status"] == "pending"
    assert partial.json()["approved_at"] is None

    approved = await post(world.compliance, path, KYC_DONE)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert approved.json()["reviewer_name"] == "cora"
    assert (await get(world.partner, path)).json()["status"] == "approved"


# ORI-05 c3: KYC older than 12 months on a running deal gives compliance a refresh task, once.
async def test_stale_kyc_on_a_running_deal_creates_a_refresh_task(world):
    running = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    closed = await create_mandate(world, world.partner, world.target_id, code_name="Osprey")
    for mandate in (running, closed):
        await post(world.compliance, f"/api/v1/mandates/{mandate['id']}/kyc", KYC_DONE)
    await post(
        world.partner,
        f"/api/v1/mandates/{closed['id']}/close",
        {"version": closed["version"], "outcome": "aborted", "abort_reason": "Seller withdrew"},
    )
    notifications = NotificationService(world.emails)

    await run_compliance_jobs(world.db, NOW + timedelta(days=364), notifications)
    assert (await get(world.compliance, "/api/v1/tasks/mine")).json() == []

    later = NOW + timedelta(days=366)
    set_clock(FrozenClock(later))
    await run_compliance_jobs(world.db, later, notifications)
    await run_compliance_jobs(world.db, later + timedelta(hours=1), notifications)

    tasks = (await get(world.compliance, "/api/v1/tasks/mine")).json()
    assert [task["title"] for task in tasks] == ["Refresh KYC for Falcon"]


# ORI-05 c4: a sanctions hit freezes the deal; only compliance unfreezes it.
async def test_a_sanctions_hit_freezes_the_deal_until_compliance_unfreezes(world):
    mandate = await create_mandate(world, world.partner, world.client_id, code_name="Falcon")
    mid = mandate["id"]

    hit = await post(world.compliance, f"/api/v1/mandates/{mid}/kyc", {**KYC_DONE, "sanctions_hit": True})
    assert hit.status_code == 200
    assert hit.json()["status"] == "frozen"
    deal = (await get(world.partner, f"/api/v1/mandates/{mid}")).json()
    assert deal["frozen"] is True
    assert deal["can_edit"] is False

    edit = await world.partner.client.patch(
        f"/api/v1/mandates/{mid}", json={"version": deal["version"], "estimated_ev": "1"}, headers=world.partner.headers
    )
    assert edit.status_code == 403
    assert "frozen" in edit.text.lower()
    assert (await post(world.partner, f"/api/v1/mandates/{mid}/unfreeze", {"reason": "Cleared"})).status_code == 403

    assert (await post(world.compliance, f"/api/v1/mandates/{mid}/unfreeze", {"reason": " "})).status_code == 422
    unfrozen = await post(world.compliance, f"/api/v1/mandates/{mid}/unfreeze", {"reason": "False positive, name match only"})
    assert unfrozen.status_code == 200, unfrozen.text
    deal = (await get(world.partner, f"/api/v1/mandates/{mid}")).json()
    assert deal["frozen"] is False
    edit = await world.partner.client.patch(
        f"/api/v1/mandates/{mid}", json={"version": deal["version"], "estimated_ev": "1"}, headers=world.partner.headers
    )
    assert edit.status_code == 200
