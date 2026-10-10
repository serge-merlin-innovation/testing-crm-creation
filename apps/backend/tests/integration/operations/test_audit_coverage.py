"""Cross-cutting (derived): every create, update and delete is written to the audit log (AUD-01)
by the same request that makes the change.

The structural test walks every mutating route and requires the audit context dependency, so a
new endpoint cannot ship without it. The behavioural tests prove the rows land for the routes
this ticket wired up.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.config.settings import settings
from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

# Not a record change: sign-in flow, session upkeep, the inbound mail webhook (its activity is
# audited by the service), read-only previews and the non-production test hooks.
NOT_RECORD_CHANGES = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/login/second-factor"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/refresh-csrf"),
    ("POST", "/api/v1/auth/session/renew"),
    ("POST", "/api/v1/oauth/token"),
    ("POST", "/api/v1/companies/lookup"),
    ("POST", "/api/v1/imports/{import_id}/preview"),
    ("PUT", "/api/v1/test-hooks/clock"),
    ("POST", "/api/v1/test-hooks/emails/capture"),
    ("POST", "/api/v1/test-hooks/jobs/run"),
}

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def _dependency_names(dependant):
    for sub in dependant.dependencies:
        yield getattr(sub.call, "__name__", "")
        yield from _dependency_names(sub)


def mutating_routes():
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        candidates = contexts() if contexts else ([route] if hasattr(route, "dependant") else [])
        for candidate in candidates:
            for method in sorted((getattr(candidate, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}):
                yield method, candidate.path, set(_dependency_names(candidate.dependant))


async def test_every_mutating_route_writes_the_audit_log():
    missing = [
        f"{method} {path}"
        for method, path, names in mutating_routes()
        if (method, path) not in NOT_RECORD_CHANGES and not names & {"get_audit_context", "get_system_audit_context"}
    ]
    assert not missing, "These change records without an audit context:\n" + "\n".join(missing)


async def test_the_guard_sees_the_routes():
    assert len(list(mutating_routes())) > 100


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    yield built
    for session in built.clients:
        await session.aclose()
    set_clock(SystemClock())


async def actions(db, record_type):
    rows = await db.execute(select(AuditEntry.action).where(AuditEntry.record_type == record_type).order_by(AuditEntry.id))
    return [action for (action,) in rows]


async def test_activity_note_and_task_changes_are_audited(world):
    partner = world.partner
    client_id = await world.company("Acme Holding")
    mandate = await create_mandate(world, partner, client_id)
    created = await partner.client.post(
        "/api/v1/activities/",
        json={
            "type": "call",
            "note": "Kick-off",
            "occurred_at": NOW.isoformat(),
            "links": [{"record_type": "mandate", "record_id": mandate["id"]}],
        },
        headers=partner.headers,
    )
    assert created.status_code == 201, created.text
    activity_id = created.json()["id"]
    edited = await partner.client.patch(
        f"/api/v1/activities/{activity_id}", json={"note": "Kick-off call"}, headers=partner.headers
    )
    assert edited.status_code == 200, edited.text
    deleted = await partner.client.delete(f"/api/v1/activities/{activity_id}", headers=partner.headers)
    assert deleted.status_code in (200, 204), deleted.text
    assert await actions(world.db, "activity") == ["activity.created", "activity.updated", "activity.deleted"]

    note = await partner.client.post(
        "/api/v1/notes/",
        json={"body": "Seller wants a quick process", "visibility": "shared", "record_type": "company", "record_id": client_id},
        headers=partner.headers,
    )
    assert note.status_code == 201, note.text
    assert await actions(world.db, "note") == ["note.created"]

    task = await partner.client.post(
        "/api/v1/tasks/",
        json={"title": "Send NDA", "due_date": "2026-10-20", "assignee_id": partner.id},
        headers=partner.headers,
    )
    assert task.status_code == 201, task.text
    done = await partner.client.post(f"/api/v1/tasks/{task.json()['id']}/complete", headers=partner.headers)
    assert done.status_code == 200, done.text
    assert await actions(world.db, "task") == ["task.created", "task.completed"]


async def test_saved_filters_and_preferences_are_audited(world):
    analyst = world.analyst
    created = await analyst.client.post(
        "/api/v1/saved-filters/", json={"name": "Brussels PE", "criteria": {"q": "capital"}}, headers=analyst.headers
    )
    assert created.status_code == 201, created.text
    filter_id = created.json()["id"]
    await analyst.client.put(f"/api/v1/saved-filters/{filter_id}/shared", json={"shared": True}, headers=analyst.headers)
    await analyst.client.delete(f"/api/v1/saved-filters/{filter_id}", headers=analyst.headers)
    assert await actions(world.db, "saved_filter") == ["saved_filter.created", "saved_filter.shared", "saved_filter.deleted"]

    response = await analyst.client.put(
        "/api/v1/notifications/preferences", json={"preferences": {"task.assigned": "email"}}, headers=analyst.headers
    )
    assert response.status_code == 200, response.text
    assert await actions(world.db, "notification_preferences") == ["notification_preferences.updated"]


async def test_the_inbound_mail_webhook_needs_no_session_and_is_audited_as_the_sender(world, client, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_EMAIL_SECRET", "hook-secret")
    address = (await world.partner.client.get("/api/v1/email-logging/address")).json()["address"]
    response = await client.post(
        "/api/v1/email-logging/inbound",
        headers={"X-Inbound-Secret": "hook-secret"},
        json={
            "sender": world.partner.email,
            "to": ["nobody@example.org"],
            "bcc": [address],
            "subject": "Hi",
            "text": "Hello",
            "spf": "pass",
            "dkim": "pass",
        },
    )
    assert response.status_code == 202, response.text
    rows = await world.db.execute(select(AuditEntry.user_id).where(AuditEntry.action == "email.unmatched"))
    assert [user_id for (user_id,) in rows] == [world.partner.id]
