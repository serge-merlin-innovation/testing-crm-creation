"""Wall-crossing requests (AUTHZ-04), delegation (AUTHZ-07), break-glass (AUTHZ-08),
the quarterly access review (ADM-05) and step-up for sensitive actions (AUTH-02 c5)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.jobs import job_runner
from src.modules.access.jobs import ACCESS_JOB, run_access_jobs
from src.modules.access.routes import REQUESTS_PER_HOUR
from src.modules.mandate.models import WallCrossing
from src.modules.notification.service import NotificationService
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate
from tests.integration.foundation.helpers import current_code, role_id

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.delegate = await built.actor("peter", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.compliance = await built.actor("cora", RoleName.COMPLIANCE)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.client_id = await built.company("Acme Holding")
    built.deal = await create_mandate(built, built.partner, built.client_id, code_name="Falcon")
    yield built
    await built.close()
    set_clock(SystemClock())


async def get(actor, path: str, **kwargs):
    return await actor.client.get(path, headers=actor.headers, **kwargs)


async def post(actor, path: str, body: dict, headers: dict | None = None):
    return await actor.client.post(path, json=body, headers={**actor.headers, **(headers or {})})


async def request_access(world, actor=None, code_name: str = "falcon", reason: str = "Sector expertise needed"):
    response = await post(actor or world.analyst, "/api/v1/access-requests/", {"code_name": code_name, "reason": reason})
    assert response.status_code == 201, response.text
    return response.json()


async def tasks(actor) -> list[dict]:
    return (await get(actor, "/api/v1/tasks/mine")).json()


async def inbox(actor) -> list[dict]:
    return (await get(actor, "/api/v1/notifications/")).json()


def step_up(actor) -> dict:
    return {"X-Step-Up-Code": current_code(actor.email)}


# AUTHZ-04 c1: knowing the code name, a request with a reason gives the deal partner and compliance an approval task.
async def test_a_request_gives_the_partner_and_compliance_an_approval_task(world):
    request = await request_access(world)

    assert request["status"] == "pending"
    for approver in (world.partner, world.compliance):
        assert [t["title"] for t in await tasks(approver)] == ["Approve wall-crossing request on Falcon"]
        queue = (await get(approver, "/api/v1/access-requests/")).json()
        assert [(r["code_name"], r["requester_name"], r["reason"]) for r in queue] == [
            ("Falcon", "anna", "Sector expertise needed")
        ]
    assert await tasks(world.delegate) == []
    missing = await post(world.analyst, "/api/v1/access-requests/", {"code_name": "Nope", "reason": "x"})
    assert missing.status_code == 404
    no_reason = await post(world.analyst, "/api/v1/access-requests/", {"code_name": "Falcon", "reason": " "})
    assert no_reason.status_code == 422


# AUTHZ-04 c2: compliance approves, the user joins with a 30-day expiry recorded in the wall-crossing register.
async def test_approval_adds_the_user_for_30_days_and_records_the_crossing(world):
    request = await request_access(world)

    decided = await post(world.compliance, f"/api/v1/access-requests/{request['id']}/decision", {"decision": "approve"})

    assert decided.status_code == 200, decided.text
    expected = (NOW + timedelta(days=30)).isoformat().replace("+00:00", "Z")
    assert decided.json()["status"] == "approved"
    deal = await get(world.analyst, f"/api/v1/mandates/{world.deal['id']}")
    assert deal.status_code == 200
    team = (await get(world.partner, f"/api/v1/mandates/{world.deal['id']}/team")).json()["members"]
    member = next(m for m in team if m["user_id"] == world.analyst.id)
    assert member["expires_at"].replace("+00:00", "Z") == expected
    crossing = (await world.db.execute(select(WallCrossing).where(WallCrossing.user_id == world.analyst.id))).scalar_one()
    assert (crossing.action, crossing.by_user_id) == ("added", world.compliance.id)
    assert crossing.expires_at == NOW + timedelta(days=30)


# AUTHZ-04 c3: when the expiry passes, access is lost automatically.
async def test_access_expires_automatically(world):
    request = await request_access(world)
    custom = (NOW + timedelta(days=10)).isoformat()
    await post(
        world.compliance, f"/api/v1/access-requests/{request['id']}/decision", {"decision": "approve", "expires_at": custom}
    )
    assert (await get(world.analyst, f"/api/v1/mandates/{world.deal['id']}")).status_code == 200

    set_clock(FrozenClock(NOW + timedelta(days=10, seconds=1)))

    assert (await get(world.analyst, f"/api/v1/mandates/{world.deal['id']}")).status_code == 404
    assert "Falcon" not in (await get(world.analyst, "/api/v1/mandates/")).text


# AUTHZ-04 c4: a rejection notifies the requester with the reason and the deal stays invisible.
async def test_rejection_notifies_with_the_reason_and_keeps_the_deal_hidden(world):
    request = await request_access(world)

    no_reason = await post(world.compliance, f"/api/v1/access-requests/{request['id']}/decision", {"decision": "reject"})
    assert no_reason.status_code == 422
    rejected = await post(
        world.compliance,
        f"/api/v1/access-requests/{request['id']}/decision",
        {"decision": "reject", "reason": "Conflicts with your buy-side mandate"},
    )

    assert rejected.status_code == 200
    notes = [n for n in await inbox(world.analyst) if n["kind"] == "access.rejected"]
    assert len(notes) == 1
    assert "Conflicts with your buy-side mandate" in notes[0]["body"]
    assert (await get(world.analyst, f"/api/v1/mandates/{world.deal['id']}")).status_code == 404
    mine = (await get(world.analyst, "/api/v1/access-requests/mine")).json()
    assert [(r["status"], r["decision_reason"]) for r in mine] == [("rejected", "Conflicts with your buy-side mandate")]


# AUTHZ-04 c5: compliance sees the requester's deals that conflict with the requested one.
async def test_compliance_sees_the_requesters_conflicting_deals(world):
    # Heron sells Northwind with Acme as target: Acme sits on the other side of Falcon, whose client it is.
    seller = await world.company("Northwind Trading")
    heron = await create_mandate(world, world.delegate, seller, code_name="Heron", target_id=world.client_id)
    cleared = await post(
        world.compliance, f"/api/v1/mandates/{heron['id']}/conflicts/decision", {"decision": "clear", "reason": "Walls"}
    )
    assert cleared.status_code == 200, cleared.text
    staffed = await post(
        world.delegate, f"/api/v1/mandates/{heron['id']}/team", {"user_id": world.analyst.id, "role": "analyst"}
    )
    assert staffed.status_code == 201
    request = await request_access(world)

    seen = (await get(world.compliance, f"/api/v1/access-requests/{request['id']}")).json()
    assert [c["code_name"] for c in seen["conflicts"]] == ["Heron"]
    partner_view = (await get(world.partner, f"/api/v1/access-requests/{request['id']}")).json()
    assert partner_view["conflicts"] == []


# AUTHZ-04 c6 (derived): the deal partner only comments; compliance decides.
async def test_the_partner_only_comments(world):
    request = await request_access(world)

    decided = await post(world.partner, f"/api/v1/access-requests/{request['id']}/decision", {"decision": "approve"})
    commented = await post(world.partner, f"/api/v1/access-requests/{request['id']}/comments", {"body": "Fine by me"})
    stranger = await post(world.delegate, f"/api/v1/access-requests/{request['id']}/comments", {"body": "Hi"})

    assert decided.status_code == 403
    assert commented.status_code == 201
    assert stranger.status_code == 404
    seen = (await get(world.compliance, f"/api/v1/access-requests/{request['id']}")).json()
    assert [(c["author_name"], c["body"], c["on_behalf_of_name"]) for c in seen["comments"]] == [("paula", "Fine by me", None)]


async def delegate(world, start: str = "2026-10-08", end: str = "2026-10-20"):
    response = await post(
        world.partner, "/api/v1/delegations/", {"delegate_id": world.delegate.id, "starts_on": start, "ends_on": end}
    )
    assert response.status_code == 201, response.text
    return response.json()


# AUTHZ-07 c1: an approval arriving during the delegation goes to the delegate and to the partner.
async def test_an_approval_in_range_goes_to_the_delegate_and_the_partner(world):
    await delegate(world)

    await request_access(world)

    for approver in (world.partner, world.delegate):
        assert [t["title"] for t in await tasks(approver)] == ["Approve wall-crossing request on Falcon"]
        assert len((await get(approver, "/api/v1/access-requests/")).json()) == 1
    assert (await get(world.partner, "/api/v1/delegations/")).json()[0]["delegate_name"] == "peter"


# AUTHZ-07 c2: delegation stops when the range ends.
async def test_delegation_stops_after_the_range(world):
    await delegate(world, end="2026-10-09")
    set_clock(FrozenClock(NOW + timedelta(days=1)))

    request = await request_access(world)

    assert await tasks(world.delegate) == []
    assert (await get(world.delegate, "/api/v1/access-requests/")).json() == []
    assert (await get(world.delegate, f"/api/v1/access-requests/{request['id']}")).status_code == 404


# AUTHZ-07 c3: what the delegate does is recorded as by the delegate on behalf of the partner.
async def test_the_delegate_acts_on_behalf_of_the_partner(world):
    await delegate(world)
    request = await request_access(world)

    response = await post(
        world.delegate, f"/api/v1/access-requests/{request['id']}/comments", {"body": "Approve", "recommendation": "approve"}
    )

    assert response.status_code == 201, response.text
    seen = (await get(world.compliance, f"/api/v1/access-requests/{request['id']}")).json()
    assert [(c["author_name"], c["on_behalf_of_name"], c["recommendation"]) for c in seen["comments"]] == [
        ("peter", "paula", "approve")
    ]
    assert seen["comments"][0]["label"] == "Approved by peter on behalf of paula"


# AUTHZ-07 c4: an unstaffed delegate sees the approval context, never the deal.
async def test_the_delegate_sees_only_the_approval_context(world):
    await delegate(world)
    request = await request_access(world)

    context = await get(world.delegate, f"/api/v1/access-requests/{request['id']}")

    assert context.status_code == 200
    assert set(context.json()) == {
        "id", "code_name", "requester_id", "requester_name", "reason", "status", "created_at", "decision_reason",
        "decided_by_name", "expires_at", "conflicts", "comments", "can_decide", "can_comment",
    }  # fmt: skip
    assert (await get(world.delegate, f"/api/v1/mandates/{world.deal['id']}")).status_code == 404
    assert (await get(world.delegate, f"/api/v1/mandates/{world.deal['id']}/team")).status_code == 404


async def break_glass(world, code: dict | None = None, reason: str = "Fix corrupted EV"):
    return await post(
        world.admin,
        "/api/v1/break-glass/",
        {"code_name": "Falcon", "reason": reason},
        headers=step_up(world.admin) if code is None else code,
    )


# AUTHZ-08 c1 + AUTH-02 c5: break-glass needs a fresh code, gives 4 hours of read and notifies compliance and the partner.
async def test_break_glass_grants_read_and_notifies(world):
    assert (await get(world.admin, f"/api/v1/mandates/{world.deal['id']}")).status_code == 404
    refused = await break_glass(world, code={})
    assert refused.status_code == 401
    assert refused.headers["X-Step-Up"] == "required"

    granted = await break_glass(world)

    assert granted.status_code == 201, granted.text
    assert granted.json()["expires_at"].startswith("2026-10-09T13:00")
    deal = await get(world.admin, f"/api/v1/mandates/{world.deal['id']}")
    assert deal.status_code == 200
    assert deal.json()["can_edit"] is False
    for watcher in (world.compliance, world.partner):
        notes = [n for n in await inbox(watcher) if n["kind"] == "access.break_glass"]
        assert len(notes) == 1
        assert "Falcon" in notes[0]["title"]
    assert (
        await post(world.admin, "/api/v1/break-glass/", {"code_name": "Falcon", "reason": ""}, step_up(world.admin))
    ).status_code == 422
    assert (
        await post(world.partner, "/api/v1/break-glass/", {"code_name": "Falcon", "reason": "x"}, step_up(world.partner))
    ).status_code == 403


# AUTHZ-08 c2: after 4 hours break-glass access is gone.
async def test_break_glass_expires_after_4_hours(world):
    await break_glass(world)
    set_clock(FrozenClock(NOW + timedelta(hours=4, seconds=1)))

    assert (await get(world.admin, f"/api/v1/mandates/{world.deal['id']}")).status_code == 404
    assert "Falcon" not in (await get(world.admin, "/api/v1/mandates/")).text


# AUTHZ-08 c3: break-glass is read-only: no edits, no team changes, no exports.
async def test_break_glass_is_read_only(world):
    await break_glass(world)
    mid = world.deal["id"]

    assert "Falcon" in (await get(world.admin, "/api/v1/mandates/")).text
    assert (await get(world.admin, f"/api/v1/mandates/{mid}/history")).status_code == 200
    edit = await world.admin.client.patch(
        f"/api/v1/mandates/{mid}", json={"version": world.deal["version"], "estimated_ev": "1"}, headers=world.admin.headers
    )
    assert edit.status_code == 403
    assert (await post(world.admin, f"/api/v1/mandates/{mid}/links", {"label": "x", "url": "https://a.b/c"})).status_code == 403
    assert (
        await post(world.admin, f"/api/v1/mandates/{mid}/team", {"user_id": world.analyst.id, "role": "analyst"})
    ).status_code == 403
    exported = await world.admin.client.get(f"/api/v1/mandates/{mid}/export", headers=world.admin.headers)
    assert exported.status_code == 403
    assert (await world.partner.client.get(f"/api/v1/mandates/{mid}/export", headers=world.partner.headers)).status_code == 200


# ADM-05 c1: at a new quarter each deal partner gets the staffed users to confirm or remove within 14 days.
async def test_a_new_quarter_opens_a_review_per_deal_partner(world):
    await post(world.partner, f"/api/v1/mandates/{world.deal['id']}/team", {"user_id": world.analyst.id, "role": "analyst"})
    notifications = NotificationService(world.emails)
    quarter = datetime(2027, 1, 1, 6, 0, tzinfo=UTC)
    set_clock(FrozenClock(quarter))

    await run_access_jobs(world.db, quarter, notifications)
    await run_access_jobs(world.db, quarter + timedelta(hours=1), notifications)

    reviews = (await get(world.partner, "/api/v1/access-reviews/")).json()
    assert len(reviews) == 1
    review = reviews[0]
    assert (review["code_name"], review["quarter"], review["due_at"][:10]) == ("Falcon", "2027-Q1", "2027-01-15")
    assert sorted(m["name"] for m in review["members"]) == ["anna", "paula"]
    assert [t["title"] for t in await tasks(world.partner)] == ["Confirm the Falcon team for 2027-Q1"]

    done = await post(world.partner, f"/api/v1/access-reviews/{review['id']}", {"remove_user_ids": [world.analyst.id]})

    assert done.status_code == 200, done.text
    assert (await get(world.analyst, f"/api/v1/mandates/{world.deal['id']}")).status_code == 404
    assert (await get(world.partner, "/api/v1/access-reviews/")).json()[0]["completed_at"] is not None
    assert ACCESS_JOB in job_runner.names


# ADM-05 c2: no answer after 14 days escalates to compliance.
async def test_an_unanswered_review_escalates_to_compliance(world):
    notifications = NotificationService(world.emails)
    quarter = datetime(2027, 1, 1, 6, 0, tzinfo=UTC)
    await run_access_jobs(world.db, quarter, notifications)

    await run_access_jobs(world.db, quarter + timedelta(days=13), notifications)
    assert not [n for n in await inbox(world.compliance) if n["kind"] == "access.review_overdue"]

    await run_access_jobs(world.db, quarter + timedelta(days=14, hours=1), notifications)
    await run_access_jobs(world.db, quarter + timedelta(days=15), notifications)
    escalations = [n for n in await inbox(world.compliance) if n["kind"] == "access.review_overdue"]
    assert len(escalations) == 1
    assert "Falcon" in escalations[0]["body"]
    overdue = (await get(world.compliance, "/api/v1/access-reviews/")).json()
    assert [r["escalated_at"] is not None for r in overdue] == [True]


# AUTH-02 c5: a role change and a mass export ask the code again within the session.
async def test_role_change_and_mass_export_need_a_fresh_code(world):
    path = f"/api/v1/users/{world.analyst.id}/role"
    body = {"role_id": await role_id(world.db, RoleName.DIRECTOR)}
    admin = world.admin

    no_code = await admin.client.patch(path, json=body, headers=admin.headers)
    wrong = await admin.client.patch(path, json=body, headers={**admin.headers, "X-Step-Up-Code": "000000"})
    ok = await admin.client.patch(path, json=body, headers={**admin.headers, **step_up(admin)})
    export_without = await admin.client.get("/api/v1/users/export", headers=admin.headers)
    export_with = await admin.client.get("/api/v1/users/export", headers={**admin.headers, **step_up(admin)})

    assert (no_code.status_code, wrong.status_code, ok.status_code) == (401, 401, 200)
    assert no_code.headers["X-Step-Up"] == "required"
    assert (export_without.status_code, export_with.status_code) == (401, 200)


async def test_guessing_code_names_is_throttled_per_user(world):
    for attempt in range(REQUESTS_PER_HOUR):
        guess = await post(world.analyst, "/api/v1/access-requests/", {"code_name": f"Guess{attempt}", "reason": "x"})
        assert guess.status_code == 404, guess.text

    throttled = await post(world.analyst, "/api/v1/access-requests/", {"code_name": "Falcon", "reason": "x"})
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) > 0
    await request_access(world, actor=world.delegate)
