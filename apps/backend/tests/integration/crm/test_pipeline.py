"""The pipeline board, stage gates, milestones, closing and closed-deal access."""

from datetime import UTC, datetime, timedelta

import pytest

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.jobs import job_runner
from src.modules.mandate.jobs import MILESTONE_JOB, notify_due_milestones
from src.modules.mandate.stages import DealStage
from src.modules.notification.service import NotificationService
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

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
    built.compliance = await built.actor("cora", RoleName.COMPLIANCE)
    built.client_id = await built.company("Acme Holding")
    built.target_id = await built.company("Widget Works")
    yield built
    await built.close()
    set_clock(SystemClock())


async def staff(world, mandate_id: int, actor, role: str) -> None:
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/team", json={"user_id": actor.id, "role": role}, headers=world.partner.headers
    )
    assert response.status_code == 201, response.text


async def current(actor, mandate_id: int) -> dict:
    return (await actor.client.get(f"/api/v1/mandates/{mandate_id}", headers=actor.headers)).json()


async def move(actor, mandate_id: int, stage: str, reason: str | None = None):
    deal = await current(actor, mandate_id)
    body = {"stage": stage, "version": deal["version"]}
    if reason is not None:
        body["reason"] = reason
    return await actor.client.post(f"/api/v1/mandates/{mandate_id}/stage", json=body, headers=actor.headers)


async def criterion(world, stage: str, kind: str, value: str | None = None):
    return await world.admin.client.post(
        "/api/v1/stage-criteria/", json={"stage": stage, "kind": kind, "value": value}, headers=world.admin.headers
    )


async def clear_builtin_gate(world) -> None:
    criteria = (await world.admin.client.get("/api/v1/stage-criteria/", headers=world.admin.headers)).json()
    for item in criteria:
        await world.admin.client.delete(f"/api/v1/stage-criteria/{item['id']}", headers=world.admin.headers)


async def at_stage(world, mandate_id: int, stage: str) -> None:
    response = await move(world.partner, mandate_id, stage)
    assert response.status_code == 200, response.text


# DEAL-02 c1: a move saves the stage and its date, and is in the deal history.
async def test_moving_a_deal_saves_stage_and_date_in_history(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    later = NOW + timedelta(days=2)
    set_clock(FrozenClock(later))

    response = await move(world.partner, mandate["id"], DealStage.PREPARATION)

    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "preparation"
    assert response.json()["stage_changed_at"] == later.isoformat().replace("+00:00", "Z")
    history = (
        await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/history", headers=world.partner.headers)
    ).json()
    assert ("stage", "conflict_review", "preparation") in {(e["field"], e["old_value"], e["new_value"]) for e in history}


# DEAL-02 c2 + DEAL-08 c1: a configured link-label criterion blocks the move, with the reason.
async def test_missing_document_link_blocks_the_move_with_the_reason(world):
    await clear_builtin_gate(world)
    mandate = await create_mandate(world, world.partner, world.client_id)
    await at_stage(world, mandate["id"], DealStage.INDICATIVE_OFFERS)
    created = await criterion(world, "indicative_offers", "link_label", "Data room")
    assert created.status_code == 201, created.text

    blocked = await move(world.partner, mandate["id"], DealStage.DUE_DILIGENCE)
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["reasons"] == ["Add a document link labelled “Data room”."]
    assert (await current(world.partner, mandate["id"]))["stage"] == "indicative_offers"

    await world.partner.client.post(
        f"/api/v1/mandates/{mandate['id']}/links",
        json={"label": "data room", "url": "https://vdr.example.com/falcon"},
        headers=world.partner.headers,
    )
    assert (await move(world.partner, mandate["id"], DealStage.DUE_DILIGENCE)).status_code == 200


# DEAL-08 c1: a required-field criterion is enforced on the next move, including when skipping stages.
async def test_required_field_criterion_is_enforced_on_the_next_move(world):
    await clear_builtin_gate(world)
    mandate = await create_mandate(world, world.partner, world.client_id)
    assert (await criterion(world, "conflict_review", "field", "target_id")).status_code == 201

    blocked = await move(world.partner, mandate["id"], DealStage.MARKETING)
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["reasons"] == ["Fill in Target."]

    deal = await current(world.partner, mandate["id"])
    await world.partner.client.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": deal["version"], "target_id": world.target_id},
        headers=world.partner.headers,
    )
    assert (await move(world.partner, mandate["id"], DealStage.MARKETING)).status_code == 200


# DEAL-08 c1: the built-in engagement letter / KYC gate sits on Preparation.
async def test_builtin_engagement_letter_and_kyc_gate_on_preparation(world):
    criteria = (await world.admin.client.get("/api/v1/stage-criteria/", headers=world.admin.headers)).json()
    assert [(c["stage"], c["kind"]) for c in criteria] == [("preparation", "kyc_engagement")]
    mandate = await create_mandate(world, world.partner, world.client_id)
    await at_stage(world, mandate["id"], DealStage.PREPARATION)

    blocked = await move(world.partner, mandate["id"], DealStage.MARKETING)

    assert blocked.status_code == 422
    assert blocked.json()["detail"]["reasons"] == [
        "Add the signed engagement letter as a document link labelled “Engagement letter”.",
        "KYC must be approved.",
    ]


async def test_only_admins_configure_stage_criteria_and_values_are_checked(world):
    response = await world.partner.client.post(
        "/api/v1/stage-criteria/",
        json={"stage": "marketing", "kind": "link_label", "value": "IM"},
        headers=world.partner.headers,
    )
    assert response.status_code == 403
    assert (await criterion(world, "marketing", "field", "favourite_colour")).status_code == 422
    assert (await criterion(world, "marketing", "link_label", "")).status_code == 422
    assert (await criterion(world, "closed_won", "link_label", "IM")).status_code == 422
    assert (await criterion(world, "marketing", "link_label", "IM")).status_code == 201
    assert (await criterion(world, "marketing", "link_label", "im")).status_code == 409


# DEAL-02 c4: a backward move needs a reason, which lands in the history.
async def test_backward_move_requires_a_reason(world):
    await clear_builtin_gate(world)
    mandate = await create_mandate(world, world.partner, world.client_id)
    await at_stage(world, mandate["id"], DealStage.MARKETING)

    missing = await move(world.partner, mandate["id"], DealStage.PREPARATION)
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["field"] == "reason"
    blank = await move(world.partner, mandate["id"], DealStage.PREPARATION, reason="  ")
    assert blank.status_code == 422

    moved = await move(world.partner, mandate["id"], DealStage.PREPARATION, reason="Client paused the sale")
    assert moved.status_code == 200
    history = (
        await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/history", headers=world.partner.headers)
    ).json()
    assert ("stage_reason", None, "Client paused the sale") in {(e["field"], e["old_value"], e["new_value"]) for e in history}


async def test_stage_moves_cannot_close_and_stale_versions_conflict(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    closing = await move(world.partner, mandate["id"], DealStage.ABORTED)
    assert closing.status_code == 422
    stale = await world.partner.client.post(
        f"/api/v1/mandates/{mandate['id']}/stage",
        json={"stage": "preparation", "version": mandate["version"] - 1},
        headers=world.partner.headers,
    )
    assert stale.status_code == 409


# DEAL-02 c3: filters by partner, type, sector and stage only ever return accessible deals.
async def test_filters_return_only_accessible_deals(world):
    await clear_builtin_gate(world)
    falcon = await create_mandate(world, world.partner, world.client_id)
    heron = await create_mandate(world, world.partner, await world.company("Qwerty Tools"), code_name="Heron", type="buy_side")
    await at_stage(world, heron["id"], DealStage.MARKETING)
    await create_mandate(world, world.outsider, await world.company("Zyxwv Unrelated"), code_name="Hidden", type="buy_side")

    async def codes(**filters) -> list[str]:
        response = await world.partner.client.get("/api/v1/mandates/", params=filters, headers=world.partner.headers)
        assert response.status_code == 200
        return [deal["code_name"] for deal in response.json()]

    assert await codes() == ["Falcon", "Heron"]
    assert await codes(type="buy_side") == ["Heron"]
    assert await codes(stage="marketing") == ["Heron"]
    assert await codes(sector_id=world.sector_id) == ["Falcon", "Heron"]
    assert await codes(partner_id=world.partner.id) == ["Falcon", "Heron"]
    assert await codes(partner_id=world.outsider.id) == []
    listed = (await world.partner.client.get("/api/v1/mandates/", headers=world.partner.headers)).json()
    assert {"lead_partner_name", "sector_id", "estimated_ev", "stage_changed_at"} <= set(listed[0])
    assert falcon["id"] in {deal["id"] for deal in listed}


# DEAL-04 c1: an actual date later than planned is late by that many days.
async def test_milestone_with_late_actual_date_reports_days_late(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    path = f"/api/v1/mandates/{mandate['id']}/milestones"
    created = await world.partner.client.post(
        path, json={"name": "IM sent", "planned_date": "2026-10-01"}, headers=world.partner.headers
    )
    assert created.status_code == 201, created.text
    milestone = created.json()
    assert milestone["late"] is True
    assert milestone["days_late"] == 9

    updated = await world.partner.client.patch(
        f"{path}/{milestone['id']}", json={"actual_date": "2026-10-05"}, headers=world.partner.headers
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["late"], updated.json()["days_late"]) == (True, 4)

    on_time = await world.partner.client.post(
        path, json={"name": "Teaser", "planned_date": "2026-10-20", "actual_date": "2026-10-08"}, headers=world.partner.headers
    )
    assert (on_time.json()["late"], on_time.json()["days_late"]) == (False, 0)
    listed = (await world.partner.client.get(path, headers=world.partner.headers)).json()
    assert [m["name"] for m in listed] == ["IM sent", "Teaser"]


# DEAL-04 c2: three days before a milestone is due, the deal team is notified, once.
async def test_team_is_notified_three_days_before_a_milestone(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.analyst, "analyst")
    path = f"/api/v1/mandates/{mandate['id']}/milestones"
    await world.partner.client.post(
        path, json={"name": "Binding offers due", "planned_date": "2026-10-14"}, headers=world.partner.headers
    )
    await world.partner.client.post(path, json={"name": "Later", "planned_date": "2026-10-30"}, headers=world.partner.headers)
    world.emails.sent.clear()
    notifications = NotificationService(world.emails)

    await notify_due_milestones(world.db, NOW, notifications)
    assert world.emails.sent == []

    three_days_before = datetime(2026, 10, 11, 7, 0, tzinfo=UTC)
    await notify_due_milestones(world.db, three_days_before, notifications)
    await notify_due_milestones(world.db, three_days_before + timedelta(hours=1), notifications)

    recipients = sorted(email.to for email in world.emails.sent)
    assert recipients == sorted([world.partner.email, world.analyst.email])
    for email in world.emails.sent:
        assert "Falcon" in email.subject
        assert "Acme" not in email.subject + email.body
    inbox = (await world.analyst.client.get("/api/v1/notifications/", headers=world.analyst.headers)).json()
    assert [n["kind"] for n in inbox if n["kind"] == "milestone.due"] == ["milestone.due"]
    assert MILESTONE_JOB in job_runner.names


async def close(actor, mandate_id: int, **body):
    deal = await current(actor, mandate_id)
    return await actor.client.post(
        f"/api/v1/mandates/{mandate_id}/close", json={"version": deal["version"], **body}, headers=actor.headers
    )


WON = {
    "outcome": "closed_won",
    "final_ev": "31000",
    "buyer": "Northwind Capital",
    "ev_ebitda": "8.5",
    "closing_date": "2026-10-09",
    "tombstone_allowed": True,
}


# DEAL-06 c1: Closed won needs final EV, buyer, EV/EBITDA, closing date and the tombstone choice.
async def test_closed_won_requires_outcome_data_and_tombstone_choice(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    for missing in ("final_ev", "buyer", "ev_ebitda", "closing_date", "tombstone_allowed"):
        body = {key: value for key, value in WON.items() if key != missing}
        response = await close(world.partner, mandate["id"], **body)
        assert response.status_code == 422, missing
        assert missing in [error["field"] for error in response.json()["errors"]]

    closed = await close(world.partner, mandate["id"], **WON)
    assert closed.status_code == 200, closed.text
    deal = closed.json()
    assert deal["stage"] == "closed_won"
    assert deal["outcome"] == {
        "final_ev": "31000.00",
        "buyer": "Northwind Capital",
        "ev_ebitda": "8.50",
        "closing_date": "2026-10-09",
        "tombstone_allowed": True,
        "abort_reason": None,
    }
    assert deal["closed_at"] is not None


async def test_only_a_partner_on_the_deal_closes_it(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.director, "director")
    response = await close(world.director, mandate["id"], **WON)
    assert response.status_code == 403


# DEAL-06 c2: Aborted needs a reason and the deal becomes read-only.
async def test_aborted_requires_a_reason_and_makes_the_deal_read_only(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.analyst, "analyst")
    missing = await close(world.partner, mandate["id"], outcome="aborted")
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["field"] == "abort_reason"

    aborted = await close(world.partner, mandate["id"], outcome="aborted", abort_reason="Seller withdrew")
    assert aborted.status_code == 200, aborted.text
    assert aborted.json()["can_edit"] is False
    deal = await current(world.analyst, mandate["id"])
    assert deal["stage"] == "aborted"

    edits = [
        ("PATCH", f"/api/v1/mandates/{mandate['id']}", {"version": deal["version"], "estimated_ev": "1"}),
        ("POST", f"/api/v1/mandates/{mandate['id']}/stage", {"version": deal["version"], "stage": "marketing"}),
        ("POST", f"/api/v1/mandates/{mandate['id']}/links", {"label": "IM", "url": "https://x.example.com/im"}),
        ("POST", f"/api/v1/mandates/{mandate['id']}/milestones", {"name": "x", "planned_date": "2026-11-01"}),
        ("POST", f"/api/v1/mandates/{mandate['id']}/team", {"user_id": world.director.id, "role": "director"}),
    ]
    for method, path, body in edits:
        for actor in (world.partner, world.analyst):
            response = await actor.client.request(method, path, json=body, headers=actor.headers)
            assert response.status_code == 403, (method, path, response.text)
            assert "closed" in response.json()["detail"]
    assert (
        await world.analyst.client.get(f"/api/v1/mandates/{mandate['id']}/links", headers=world.analyst.headers)
    ).status_code == 200


# DEAL-06 c3: reopening needs a reason and is audited.
async def test_reopening_needs_a_reason_and_is_audited(world):
    await clear_builtin_gate(world)
    mandate = await create_mandate(world, world.partner, world.client_id)
    await at_stage(world, mandate["id"], DealStage.SIGNING)
    await close(world.partner, mandate["id"], outcome="aborted", abort_reason="Seller withdrew")
    path = f"/api/v1/mandates/{mandate['id']}/reopen"

    deal = await current(world.partner, mandate["id"])
    missing = await world.partner.client.post(path, json={"version": deal["version"]}, headers=world.partner.headers)
    assert missing.status_code == 422
    blank = await world.partner.client.post(
        path, json={"version": deal["version"], "reason": " "}, headers=world.partner.headers
    )
    assert blank.status_code == 422
    reopened = await world.partner.client.post(
        path, json={"version": deal["version"], "reason": "Seller is back"}, headers=world.partner.headers
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["stage"] == "signing"
    assert reopened.json()["can_edit"] is True
    assert reopened.json()["outcome"]["abort_reason"] is None

    audit = (
        await world.compliance.client.get(
            "/api/v1/audit/",
            params={"record_type": "mandate", "record_id": mandate["id"], "action": "mandate.reopened"},
            headers=world.compliance.headers,
        )
    ).json()
    entries = audit["data"]
    assert len(entries) == 1
    assert entries[0]["new_values"]["reason"] == "Seller is back"
    assert entries[0]["user_id"] == world.partner.id


async def test_an_open_deal_cannot_be_reopened(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate['id']}/reopen",
        json={"version": mandate["version"], "reason": "why"},
        headers=world.partner.headers,
    )
    assert response.status_code == 422


# AUTHZ-02 c7 + c8: 12 months after closing, only the former team and compliance (read-only) see the deal.
async def test_twelve_months_after_closing_only_former_team_and_compliance_read(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.analyst, "analyst")
    await close(world.partner, mandate["id"], **WON)
    deal_path = f"/api/v1/mandates/{mandate['id']}"

    set_clock(FrozenClock(NOW + timedelta(days=200)))
    assert (await world.compliance.client.get(deal_path, headers=world.compliance.headers)).status_code == 404

    set_clock(FrozenClock(datetime(2027, 10, 11, 9, 0, tzinfo=UTC)))
    for staffed in (world.partner, world.analyst):
        assert (await staffed.client.get(deal_path, headers=staffed.headers)).status_code == 200
    for outsider in (world.outsider, world.director, world.admin):
        assert (await outsider.client.get(deal_path, headers=outsider.headers)).status_code == 404
        listed = (await outsider.client.get("/api/v1/mandates/", headers=outsider.headers)).json()
        assert listed == []

    compliance = world.compliance
    opened = await compliance.client.get(deal_path, headers=compliance.headers)
    assert opened.status_code == 200
    assert (opened.json()["can_edit"], opened.json()["can_manage_team"]) == (False, False)
    assert [d["code_name"] for d in (await compliance.client.get("/api/v1/mandates/", headers=compliance.headers)).json()] == [
        "Falcon"
    ]
    for read in ("history", "team", "links", "milestones", "wall-crossings"):
        assert (await compliance.client.get(f"{deal_path}/{read}", headers=compliance.headers)).status_code == 200, read
    deal = opened.json()
    writes = [
        ("PATCH", deal_path, {"version": deal["version"], "estimated_ev": "1"}),
        ("POST", f"{deal_path}/reopen", {"version": deal["version"], "reason": "audit"}),
        ("POST", f"{deal_path}/links", {"label": "IM", "url": "https://x.example.com/im"}),
        ("POST", f"{deal_path}/team", {"user_id": compliance.id, "role": "other"}),
    ]
    for method, path, body in writes:
        response = await compliance.client.request(method, path, json=body, headers=compliance.headers)
        assert response.status_code == 403, (method, path, response.text)
