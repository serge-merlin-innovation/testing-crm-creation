"""ACT-01, ACT-02, ACT-03, ACT-06 and AUTHZ-02 c2: activities, notes, tasks and notification preferences."""

from datetime import UTC, datetime, timedelta

import pytest

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.jobs import job_runner
from src.modules.notification.service import NotificationService
from src.modules.role.permissions import RoleName
from src.modules.task.jobs import DIGEST_JOB
from src.modules.task.service import TaskService
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    clock = FrozenClock(NOW)
    set_clock(clock)
    built = await build_world(seeded_db)
    built.clock = clock
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.client_id = await built.company("Acme Holding")
    response = await built.partner.client.post(
        "/api/v1/contacts/",
        json={"first_name": "Jan", "last_name": "Peeters", "source": "Forum", "company_id": built.client_id},
        headers=built.partner.headers,
    )
    built.contact_id = response.json()["id"]
    built.mandate = await create_mandate(built, built.partner, built.client_id)
    await built.partner.client.post(
        f"/api/v1/mandates/{built.mandate['id']}/team",
        json={"user_id": built.analyst.id, "role": "analyst"},
        headers=built.partner.headers,
    )
    built.emails.sent.clear()
    yield built
    await built.close()
    set_clock(SystemClock())


async def log(world, actor, links, note="Discussed timing", **extra):
    response = await actor.client.post(
        "/api/v1/activities/",
        json={
            "type": "call",
            "occurred_at": NOW.isoformat(),
            "participants": ["Jan Peeters", "Paula"],
            "note": note,
            "links": links,
            **extra,
        },
        headers=actor.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def timeline(actor, record_type, record_id):
    response = await actor.client.get(f"/api/v1/timeline/{record_type}/{record_id}", headers=actor.headers)
    assert response.status_code == 200, response.text
    return response.json()


def ref(record_type, record_id):
    return {"record_type": record_type, "record_id": record_id}


# ACT-01 c1
async def test_activity_shows_on_every_linked_timeline(world):
    activity = await log(world, world.partner, [ref("contact", world.contact_id), ref("company", world.client_id)])
    assert activity["participants"] == ["Jan Peeters", "Paula"]
    for record_type, record_id in (("contact", world.contact_id), ("company", world.client_id)):
        shown = (await timeline(world.analyst, record_type, record_id))["activities"]
        assert [a["id"] for a in shown] == [activity["id"]]
        assert shown[0]["type"] == "call"
        assert shown[0]["note"] == "Discussed timing"


# ACT-01 c2 (AUTHZ-02)
async def test_deal_linked_activity_is_hidden_from_non_staffed_on_the_contact(world):
    activity = await log(world, world.partner, [ref("contact", world.contact_id), ref("mandate", world.mandate["id"])])
    staffed = await timeline(world.analyst, "contact", world.contact_id)
    assert [a["id"] for a in staffed["activities"]] == [activity["id"]]
    for outsider in (world.outsider, world.admin):
        response = await outsider.client.get(f"/api/v1/timeline/contact/{world.contact_id}", headers=outsider.headers)
        assert response.json()["activities"] == []
        assert "Discussed timing" not in response.text
    hidden = await world.outsider.client.get(f"/api/v1/timeline/mandate/{world.mandate['id']}", headers=world.outsider.headers)
    assert hidden.status_code == 404


async def test_non_staffed_user_cannot_log_against_a_deal(world):
    response = await world.outsider.client.post(
        "/api/v1/activities/",
        json={"type": "call", "occurred_at": NOW.isoformat(), "note": "x", "links": [ref("mandate", world.mandate["id"])]},
        headers=world.outsider.headers,
    )
    assert response.status_code == 404


# ACT-01 c3
async def test_edit_after_seven_days_is_shown_as_edited_with_date(world):
    activity = await log(world, world.partner, [ref("contact", world.contact_id)])
    world.clock.advance(timedelta(days=2))
    early = await world.partner.client.patch(
        f"/api/v1/activities/{activity['id']}", json={"note": "Typo fixed"}, headers=world.partner.headers
    )
    assert early.json()["edited_at"] is None
    world.clock.advance(timedelta(days=6))
    late = await world.partner.client.patch(
        f"/api/v1/activities/{activity['id']}", json={"note": "Revised"}, headers=world.partner.headers
    )
    assert late.status_code == 200
    edited_at = world.clock.now().isoformat().replace("+00:00", "Z")
    assert late.json()["edited_at"] in (edited_at, world.clock.now().isoformat())
    shown = (await timeline(world.partner, "contact", world.contact_id))["activities"][0]
    assert shown["edited_at"] is not None
    assert shown["note"] == "Revised"


async def test_only_the_author_edits(world):
    activity = await log(world, world.partner, [ref("contact", world.contact_id)])
    response = await world.analyst.client.patch(
        f"/api/v1/activities/{activity['id']}", json={"note": "Mine now"}, headers=world.analyst.headers
    )
    assert response.status_code == 403


# ACT-01 c4
async def test_delete_is_soft_and_admin_restores_within_thirty_days(world):
    activity = await log(world, world.partner, [ref("contact", world.contact_id)])
    deleted = await world.partner.client.delete(f"/api/v1/activities/{activity['id']}", headers=world.partner.headers)
    assert deleted.status_code == 204
    assert (await timeline(world.partner, "contact", world.contact_id))["activities"] == []

    bin_ = await world.admin.client.get("/api/v1/activities/deleted", headers=world.admin.headers)
    assert [a["id"] for a in bin_.json()] == [activity["id"]]
    denied = await world.partner.client.post(f"/api/v1/activities/{activity['id']}/restore", headers=world.partner.headers)
    assert denied.status_code == 403

    world.clock.advance(timedelta(days=29))
    restored = await world.admin.client.post(f"/api/v1/activities/{activity['id']}/restore", headers=world.admin.headers)
    assert restored.status_code == 204
    assert [a["id"] for a in (await timeline(world.partner, "contact", world.contact_id))["activities"]] == [activity["id"]]


async def test_restore_is_refused_after_thirty_days(world):
    activity = await log(world, world.partner, [ref("contact", world.contact_id)])
    await world.partner.client.delete(f"/api/v1/activities/{activity['id']}", headers=world.partner.headers)
    world.clock.advance(timedelta(days=31))
    response = await world.admin.client.post(f"/api/v1/activities/{activity['id']}/restore", headers=world.admin.headers)
    assert response.status_code == 409
    bin_ = await world.admin.client.get("/api/v1/activities/deleted", headers=world.admin.headers)
    assert bin_.json() == []


async def add_note(actor, record_type, record_id, body, visibility, **extra):
    response = await actor.client.post(
        "/api/v1/notes/",
        json={"record_type": record_type, "record_id": record_id, "body": body, "visibility": visibility, **extra},
        headers=actor.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ACT-02 c1
async def test_private_note_is_shown_to_its_author_only_admins_included(world):
    await add_note(world.partner, "contact", world.contact_id, "Thinks CEO will sell", "private")
    await add_note(world.partner, "contact", world.contact_id, "Met at forum", "shared")
    mine = await timeline(world.partner, "contact", world.contact_id)
    assert {n["body"] for n in mine["notes"]} == {"Thinks CEO will sell", "Met at forum"}
    for other in (world.analyst, world.outsider, world.admin):
        response = await other.client.get(f"/api/v1/timeline/contact/{world.contact_id}", headers=other.headers)
        assert [n["body"] for n in response.json()["notes"]] == ["Met at forum"]
        assert "CEO will sell" not in response.text


# ACT-02 c2 (derived)
async def test_deal_confidential_note_is_hidden_from_non_team_on_shared_records(world):
    mandate_id = world.mandate["id"]
    await add_note(world.analyst, "company", world.client_id, "Wants 8x EBITDA", "deal_confidential", mandate_id=mandate_id)
    await add_note(world.analyst, "contact", world.contact_id, "Key decision maker", "deal_confidential", mandate_id=mandate_id)
    for record_type, record_id in (("company", world.client_id), ("contact", world.contact_id)):
        assert len((await timeline(world.partner, record_type, record_id))["notes"]) == 1
        response = await world.outsider.client.get(
            f"/api/v1/timeline/{record_type}/{record_id}", headers=world.outsider.headers
        )
        assert response.json()["notes"] == []


async def test_deal_confidential_note_needs_its_deal(world):
    response = await world.partner.client.post(
        "/api/v1/notes/",
        json={"record_type": "company", "record_id": world.client_id, "body": "x", "visibility": "deal_confidential"},
        headers=world.partner.headers,
    )
    assert response.status_code == 422
    outsider = await world.outsider.client.post(
        "/api/v1/notes/",
        json={
            "record_type": "company",
            "record_id": world.client_id,
            "body": "x",
            "visibility": "deal_confidential",
            "mandate_id": world.mandate["id"],
        },
        headers=world.outsider.headers,
    )
    assert outsider.status_code == 404


# AUTHZ-02 c2
async def test_non_staffed_user_sees_neither_deal_link_nor_deal_notes_on_shared_company(world):
    await add_note(world.partner, "mandate", world.mandate["id"], "Falcon pricing view", "shared")
    await add_note(
        world.partner, "company", world.client_id, "Falcon round 2", "deal_confidential", mandate_id=world.mandate["id"]
    )
    staffed = await timeline(world.analyst, "company", world.client_id)
    assert staffed["deals"] == [{"id": world.mandate["id"], "code_name": "Falcon"}]
    assert len(staffed["notes"]) == 1
    response = await world.outsider.client.get(f"/api/v1/timeline/company/{world.client_id}", headers=world.outsider.headers)
    assert response.status_code == 200
    assert response.json()["deals"] == []
    assert response.json()["notes"] == []
    assert "Falcon" not in response.text


async def overdue_digest(world, now):
    await TaskService(NotificationService(world.emails)).send_overdue_digests(world.db, now)


async def make_task(actor, **body):
    payload = {"title": "Send teaser", "due_date": "2026-10-15", **body}
    return await actor.client.post("/api/v1/tasks/", json=payload, headers=actor.headers)


# ACT-03 c1
async def test_assigned_task_notifies_and_appears_in_my_tasks(world):
    response = await make_task(world.partner, assignee_id=world.analyst.id, record_type="contact", record_id=world.contact_id)
    assert response.status_code == 201, response.text
    task = response.json()
    mine = await world.analyst.client.get("/api/v1/tasks/mine", headers=world.analyst.headers)
    assert [t["id"] for t in mine.json()] == [task["id"]]
    notes = await world.analyst.client.get("/api/v1/notifications/", headers=world.analyst.headers)
    assert "task.assigned" in [n["kind"] for n in notes.json()]
    assert [e.to for e in world.emails.sent] == [world.analyst.email]


# ACT-03 c2
async def test_overdue_tasks_trigger_one_daily_digest(world):
    await make_task(world.partner, assignee_id=world.analyst.id, title="Call bank", due_date="2026-10-09")
    await make_task(world.partner, assignee_id=world.analyst.id, title="Later", due_date="2026-10-20")
    world.emails.sent.clear()
    next_morning = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)
    await overdue_digest(world, next_morning)
    await overdue_digest(world, next_morning + timedelta(hours=1))
    digests = [e for e in world.emails.sent if e.to == world.analyst.email]
    assert len(digests) == 1
    assert "Call bank" in digests[0].body
    assert "Later" not in digests[0].body
    await overdue_digest(world, next_morning + timedelta(days=1))
    assert len([e for e in world.emails.sent if e.to == world.analyst.email]) == 2


async def test_overdue_digest_is_a_scheduled_job():
    assert DIGEST_JOB in job_runner.names


# ACT-03 c3
async def test_deal_task_cannot_go_to_a_non_staffed_user(world):
    blocked = await make_task(
        world.partner, assignee_id=world.outsider.id, record_type="mandate", record_id=world.mandate["id"]
    )
    assert blocked.status_code == 422
    assert blocked.json()["errors"][0]["field"] == "assignee_id"
    allowed = await make_task(world.partner, assignee_id=world.analyst.id, record_type="mandate", record_id=world.mandate["id"])
    assert allowed.status_code == 201


# ACT-03 c4
async def test_completing_a_recurring_task_creates_the_next(world):
    task = (
        await make_task(world.partner, assignee_id=world.analyst.id, title="Weekly client update", recurrence="weekly")
    ).json()
    done = await world.analyst.client.post(f"/api/v1/tasks/{task['id']}/complete", headers=world.analyst.headers)
    assert done.json()["completed_at"] is not None
    mine = (await world.analyst.client.get("/api/v1/tasks/mine", headers=world.analyst.headers)).json()
    assert [(t["title"], t["due_date"], t["recurrence"]) for t in mine] == [("Weekly client update", "2026-10-22", "weekly")]
    again = await world.analyst.client.post(f"/api/v1/tasks/{task['id']}/complete", headers=world.analyst.headers)
    assert again.status_code == 200
    assert len((await world.analyst.client.get("/api/v1/tasks/mine", headers=world.analyst.headers)).json()) == 1


# ACT-06 c1
@pytest.mark.parametrize(("channel", "in_app", "email"), [("in_app", 1, 0), ("email", 0, 1), ("none", 0, 0), ("both", 1, 1)])
async def test_notifications_follow_the_chosen_channel(world, channel, in_app, email):
    saved = await world.analyst.client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": {"task.assigned": channel}},
        headers=world.analyst.headers,
    )
    assert {p["kind"]: p["channel"] for p in saved.json()}["task.assigned"] == channel
    await make_task(world.partner, assignee_id=world.analyst.id)
    rows = (await world.analyst.client.get("/api/v1/notifications/", headers=world.analyst.headers)).json()
    assert len([row for row in rows if row["kind"] == "task.assigned"]) == in_app
    assert len([e for e in world.emails.sent if e.to == world.analyst.email]) == email


# ACT-06 c2
async def test_deal_notification_email_uses_the_code_name_only(world):
    await make_task(
        world.partner,
        assignee_id=world.analyst.id,
        title="Chase Acme Holding CFO",
        record_type="mandate",
        record_id=world.mandate["id"],
        due_date="2026-10-09",
    )
    await overdue_digest(world, datetime(2026, 10, 11, 6, 0, tzinfo=UTC))
    sent = [e for e in world.emails.sent if e.to == world.analyst.email]
    assert len(sent) == 2
    for email in sent:
        assert "Falcon" in email.subject + email.body
        assert "Acme" not in email.subject + email.body
