"""AUTH-05, ADM-03, GDPR-02, GDPR-03, REP-06: offboarding, person export and erasure, retention, export controls."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.email import InMemoryEmailSender, LoggingEmailSender, set_email_sender
from src.infrastructure.jobs import job_runner
from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.contact.models import Contact
from src.modules.notification.models import Notification
from src.modules.notification.service import NotificationService
from src.modules.privacy.jobs import MONTHLY, RETENTION_JOB
from src.modules.privacy.service import PrivacyService
from src.modules.role.permissions import RoleName
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
    built.partner2 = await built.actor("pieter", RoleName.PARTNER)
    built.admin = await built.actor("adam", RoleName.ADMIN)
    built.compliance = await built.actor("carla", RoleName.COMPLIANCE)
    built.client_id = await built.company("Acme Holding")
    yield built
    await built.close()
    set_clock(SystemClock())


def anonymous(world) -> AsyncClient:
    session = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    world.clients.append(session)
    return session


async def contact(actor, first="Jan", last="Peeters", **extra) -> int:
    response = await actor.client.post(
        "/api/v1/contacts/",
        json={"first_name": first, "last_name": last, "source": "Forum", **extra},
        headers=actor.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def staff(world, mandate_id: int, user_id: int, role: str = "analyst") -> None:
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate_id}/team", json={"user_id": user_id, "role": role}, headers=world.partner.headers
    )
    assert response.status_code == 201, response.text


async def deactivate(world, user_id: int, new_owner_id: int | None = None):
    return await world.admin.client.post(
        f"/api/v1/users/{user_id}/deactivate", json={"new_owner_id": new_owner_id}, headers=world.admin.headers
    )


# AUTH-05 c1: sessions end immediately, next request refused.
async def test_deactivation_ends_every_session_and_the_next_request_is_refused(world):
    assert (await world.analyst.client.get("/api/v1/users/me")).status_code == 200

    response = await deactivate(world, world.analyst.id)

    assert response.status_code == 200, response.text
    assert response.json()["sessions_ended"] >= 1
    assert (await world.analyst.client.get("/api/v1/users/me")).status_code == 401


# AUTH-05 c2: no reset email for a deactivated user.
async def test_a_deactivated_user_gets_no_password_reset_email(world):
    mailbox = InMemoryEmailSender()
    set_email_sender(mailbox)
    try:
        await deactivate(world, world.analyst.id)
        response = await anonymous(world).post("/api/v1/auth/password/forgot", json={"email": world.analyst.email})
        assert response.status_code == 202
        assert mailbox.to(world.analyst.email) == []
    finally:
        set_email_sender(LoggingEmailSender())


# AUTH-05 c3: API tokens revoked.
async def test_deactivation_revokes_every_api_token(world):
    issued = await world.analyst.client.post("/api/v1/api-tokens/", json={"name": "BI"}, headers=world.analyst.headers)
    token = issued.json()["token"]
    api = anonymous(world)
    assert (await api.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200

    response = await deactivate(world, world.analyst.id)

    assert response.json()["api_tokens_revoked"] == 1
    assert (await api.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401


# AUTH-05 c4 / ADM-03: the confirmation lists sessions ended and records awaiting reassignment.
async def test_the_admin_sees_a_confirmation_of_sessions_ended_and_records_reassigned(world):
    contact_id = await contact(world.analyst)

    preview = (await world.admin.client.get(f"/api/v1/users/{world.analyst.id}/offboarding")).json()
    assert preview["needs_new_owner"] is True
    assert [c["id"] for c in preview["contacts"]] == [contact_id]

    response = await deactivate(world, world.analyst.id, world.partner2.id)

    body = response.json()
    assert body["sessions_ended"] >= 1
    assert body["new_owner_name"] == "pieter"
    assert {"type": "contact", "id": contact_id, "label": "Jan Peeters"} in body["reassigned"]
    again = await world.admin.client.get(f"/api/v1/users/{world.analyst.id}/offboarding/confirmation")
    assert again.json()["reassigned"] == body["reassigned"]


# ADM-03 c1: owned contacts, tasks or deals need a new owner first.
async def test_a_new_owner_is_required_when_the_leaver_owns_contacts_tasks_or_deals(world):
    contact_id = await contact(world.partner)
    mandate = await create_mandate(world, world.partner, world.client_id)
    task = await world.analyst.client.post(
        "/api/v1/tasks/",
        json={"title": "Call back", "due_date": "2026-10-15", "assignee_id": world.partner.id},
        headers=world.analyst.headers,
    )
    assert task.status_code == 201, task.text

    refused = await deactivate(world, world.partner.id)
    assert refused.status_code == 422
    assert (await world.partner.client.get("/api/v1/users/me")).status_code == 200
    not_partner = await deactivate(world, world.partner.id, world.analyst.id)
    assert not_partner.status_code == 422

    done = await deactivate(world, world.partner.id, world.partner2.id)

    assert done.status_code == 200, done.text
    types = {(r["type"], r["id"]) for r in done.json()["reassigned"]}
    assert {("contact", contact_id), ("deal", mandate["id"]), ("task", task.json()["id"])} <= types
    assert (await world.db.get(Contact, contact_id)).owner_id == world.partner2.id
    deal = await world.partner2.client.get(f"/api/v1/mandates/{mandate['id']}")
    assert deal.status_code == 200
    assert deal.json()["lead_partner_id"] == world.partner2.id
    tasks = (await world.partner2.client.get("/api/v1/tasks/mine")).json()
    assert task.json()["id"] in [t["id"] for t in tasks]


async def test_nothing_owned_means_no_owner_is_asked(world):
    response = await deactivate(world, world.analyst.id)
    assert response.status_code == 200
    assert response.json()["reassigned"] == []


# ADM-03 c2: history stays visible, labelled (inactive).
async def test_a_deactivated_users_history_stays_visible_labelled_inactive(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.analyst.id)
    contact_id = await contact(world.partner)
    logged = await world.analyst.client.post(
        "/api/v1/activities/",
        json={
            "type": "call",
            "occurred_at": NOW.isoformat(),
            "note": "Intro call",
            "links": [{"record_type": "contact", "record_id": contact_id}],
        },
        headers=world.analyst.headers,
    )
    assert logged.status_code == 201, logged.text

    await deactivate(world, world.analyst.id)

    timeline = (await world.partner.client.get(f"/api/v1/timeline/contact/{contact_id}")).json()
    assert timeline["activities"][0]["author_name"] == "anna (inactive)"
    crossings = (await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/wall-crossings")).json()
    assert {c["user_name"] for c in crossings if c["user_id"] == world.analyst.id} == {"anna (inactive)"}


# ADM-03 c3: reactivation restores the role, not the deal team memberships.
async def test_reactivation_restores_the_role_but_no_deal_team_membership(world):
    mandate = await create_mandate(world, world.partner, world.client_id)
    await staff(world, mandate["id"], world.analyst.id)
    await deactivate(world, world.analyst.id)

    response = await world.admin.client.post(f"/api/v1/users/{world.analyst.id}/reactivate", headers=world.admin.headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"user_id": world.analyst.id, "role_name": RoleName.ANALYST.value, "deal_memberships": 0}
    team = (await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}/team")).json()
    assert world.analyst.id not in [m["user_id"] for m in team["members"]]


async def test_the_admin_list_shows_deactivated_users_for_reactivation(world):
    await deactivate(world, world.analyst.id)

    inactive = (await world.admin.client.get("/api/v1/users/", params={"status": "inactive"})).json()["data"]
    active = (await world.admin.client.get("/api/v1/users/")).json()["data"]

    assert [(u["id"], u["status"]) for u in inactive] == [(world.analyst.id, "inactive")]
    assert world.analyst.id not in [u["id"] for u in active]


async def test_only_admins_offboard(world):
    assert (
        await world.partner.client.post(f"/api/v1/users/{world.analyst.id}/deactivate", json={}, headers=world.partner.headers)
    ).status_code == 403


# GDPR-02 c1: Export person produces all data and activities as a file.
async def test_export_person_produces_all_data_and_activities_as_a_file(world):
    contact_id = await contact(world.partner, email="jan@acme.be")
    await world.partner.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": NOW.isoformat(),
            "note": "Lunch with Jan",
            "links": [{"record_type": "contact", "record_id": contact_id}],
        },
        headers=world.partner.headers,
    )
    await world.partner.client.post(
        "/api/v1/notes/",
        json={"record_type": "contact", "record_id": contact_id, "body": "Prefers mornings", "visibility": "shared"},
        headers=world.partner.headers,
    )

    response = await world.compliance.client.get(f"/api/v1/contacts/{contact_id}/export")

    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    document = json.loads(response.text)
    assert document["contact"]["email"] == "jan@acme.be"
    assert document["activities"][0]["note"] == "Lunch with Jan"
    assert document["notes"][0]["body"] == "Prefers mornings"
    assert (await world.analyst.client.get(f"/api/v1/contacts/{contact_id}/export")).status_code == 403


# GDPR-02 c2: erasure anonymises; activities keep non-personal content.
async def test_erasure_anonymises_personal_fields_and_keeps_non_personal_activity_content(world):
    contact_id = await contact(world.partner, email="jan@acme.be", phone="+32 2 555 12 34")
    await world.partner.client.post(
        "/api/v1/activities/",
        json={
            "type": "call",
            "occurred_at": NOW.isoformat(),
            "participants": ["Jan Peeters", "paula"],
            "note": "Jan Peeters discussed the sale timeline",
            "links": [{"record_type": "contact", "record_id": contact_id}],
        },
        headers=world.partner.headers,
    )

    response = await world.compliance.client.post(f"/api/v1/contacts/{contact_id}/erase", headers=world.compliance.headers)

    assert response.status_code == 200, response.text
    erased = (await world.partner.client.get(f"/api/v1/contacts/{contact_id}")).json()
    assert erased["first_name"] == "Erased"
    assert erased["email"] is None
    assert erased["phone"] is None
    activity = (await world.partner.client.get(f"/api/v1/timeline/contact/{contact_id}")).json()["activities"][0]
    assert "Peeters" not in activity["note"]
    assert "discussed the sale timeline" in activity["note"]
    assert activity["participants"] == ["[erased]", "paula"]


async def test_erasure_is_blocked_with_the_reason_when_a_legal_hold_applies(world):
    contact_id = await contact(world.partner)
    hold = await world.compliance.client.post(
        f"/api/v1/contacts/{contact_id}/legal-holds",
        json={"reason": "AML 10-year retention", "until": (NOW + timedelta(days=3650)).isoformat()},
        headers=world.compliance.headers,
    )
    assert hold.status_code == 201, hold.text

    response = await world.compliance.client.post(f"/api/v1/contacts/{contact_id}/erase", headers=world.compliance.headers)

    assert response.status_code == 409
    assert "AML 10-year retention" in response.json()["detail"]
    assert (await world.partner.client.get(f"/api/v1/contacts/{contact_id}")).json()["first_name"] == "Jan"

    await world.compliance.client.delete(f"/api/v1/legal-holds/{hold.json()['id']}", headers=world.compliance.headers)
    assert (
        await world.compliance.client.post(f"/api/v1/contacts/{contact_id}/erase", headers=world.compliance.headers)
    ).status_code == 200


# GDPR-03: monthly job asks the owner to keep or anonymise after 5 years (configurable).
async def test_the_monthly_job_asks_the_owner_to_keep_or_anonymise_an_inactive_contact(world):
    stale = await contact(world.partner, first="Old", last="Friend")
    fresh = await contact(world.partner, first="New", last="Friend")
    await world.db.execute(
        Contact.__table__.update().where(Contact.id == stale).values(created_at=NOW - timedelta(days=365 * 5 + 10))
    )
    await world.db.commit()

    asked = await PrivacyService(NotificationService(world.emails)).ask_owners(world.db, NOW)

    assert asked == 1
    reviews = (await world.partner.client.get("/api/v1/privacy/retention-reviews")).json()
    assert [r["contact_id"] for r in reviews] == [stale]
    assert fresh not in [r["contact_id"] for r in reviews]
    titles = (await world.db.execute(select(Notification.title).where(Notification.user_id == world.partner.id))).scalars()
    assert "Keep or anonymise an inactive contact" in list(titles)
    assert await PrivacyService(NotificationService(world.emails)).ask_owners(world.db, NOW) == 0

    kept = await world.partner.client.post(
        f"/api/v1/privacy/retention-reviews/{reviews[0]['id']}", json={"decision": "keep"}, headers=world.partner.headers
    )
    assert kept.status_code == 204
    assert (await world.partner.client.get("/api/v1/privacy/retention-reviews")).json() == []


async def test_the_inactivity_period_is_configurable_and_the_job_is_monthly(world):
    assert job_runner._jobs[RETENTION_JOB].interval == MONTHLY
    two_years = await contact(world.partner)
    await world.db.execute(
        Contact.__table__.update().where(Contact.id == two_years).values(created_at=NOW - timedelta(days=800))
    )
    await world.db.commit()
    response = await world.compliance.client.put(
        "/api/v1/privacy/retention-policy", json={"inactive_years": 2}, headers=world.compliance.headers
    )
    assert response.status_code == 200

    assert await PrivacyService(NotificationService(world.emails)).ask_owners(world.db, NOW) == 1


async def test_anonymise_decision_erases_the_contact(world):
    stale = await contact(world.partner)
    await world.db.execute(
        Contact.__table__.update().where(Contact.id == stale).values(created_at=NOW - timedelta(days=365 * 6))
    )
    await world.db.commit()
    await PrivacyService(NotificationService(world.emails)).ask_owners(world.db, NOW)
    review = (await world.partner.client.get("/api/v1/privacy/retention-reviews")).json()[0]

    await world.partner.client.post(
        f"/api/v1/privacy/retention-reviews/{review['id']}", json={"decision": "anonymise"}, headers=world.partner.headers
    )

    assert (await world.partner.client.get(f"/api/v1/contacts/{stale}")).json()["first_name"] == "Erased"


async def bulk_contacts(world, count: int) -> None:
    await world.db.execute(
        insert(Contact),
        [
            {"first_name": f"Bulk{i}", "last_name": "Row", "source": "Import", "language": "en", "created_at": NOW}
            for i in range(count)
        ],
    )
    await world.db.commit()


# REP-06 c1: an analyst exporting more than 500 contacts needs partner approval.
async def test_an_analyst_exporting_more_than_500_contacts_needs_partner_approval(world):
    await bulk_contacts(world, 501)

    refused = await world.analyst.client.get("/api/v1/exports/contacts")
    assert refused.status_code == 403
    assert "approval" in refused.json()["detail"]

    requested = await world.analyst.client.post(
        "/api/v1/exports/approvals", json={"reason": "Event mailing"}, headers=world.analyst.headers
    )
    assert requested.status_code == 201, requested.text
    approval_id = requested.json()["id"]
    assert (
        await world.analyst.client.post(
            f"/api/v1/exports/approvals/{approval_id}", json={"approve": True}, headers=world.analyst.headers
        )
    ).status_code == 403
    approved = await world.partner.client.post(
        f"/api/v1/exports/approvals/{approval_id}", json={"approve": True}, headers=world.partner.headers
    )
    assert approved.json()["status"] == "approved"

    allowed = await world.analyst.client.get("/api/v1/exports/contacts")
    assert allowed.status_code == 200
    assert len(allowed.text.strip().splitlines()) == 502
    assert (await world.analyst.client.get("/api/v1/exports/contacts")).status_code == 403


async def test_500_contacts_or_a_non_analyst_export_needs_no_approval(world):
    await bulk_contacts(world, 500)
    assert (await world.analyst.client.get("/api/v1/exports/contacts")).status_code == 200
    await bulk_contacts(world, 1)
    assert (await world.partner.client.get("/api/v1/exports/contacts")).status_code == 200


# REP-06 c2: every export logs user, time, filter and row count.
async def test_every_export_logs_user_time_filter_and_row_count(world):
    await bulk_contacts(world, 3)
    await contact(world.partner, first="Zed", last="Unique")

    response = await world.partner.client.get("/api/v1/exports/contacts", params={"q": "Bulk"})

    assert response.status_code == 200
    entry = (
        await world.db.execute(select(AuditEntry).where(AuditEntry.action == "export", AuditEntry.record_type == "contacts"))
    ).scalar_one()
    assert entry.user_id == world.partner.id
    assert entry.created_at == NOW
    assert entry.new_values["filter"] == {"q": "Bulk"}
    assert entry.new_values["rows"] == 3


# Review S2 (decision 70): the person file leaves out other users' private notes (ACT-02 c1) and names a
# deal by its code name only (AUTHZ-06 c2), so it carries no deal id, client or target.
async def test_export_person_excludes_others_private_notes_and_names_deals_by_code_name(world):
    contact_id = await contact(world.partner, email="jan@acme.be")
    mandate = await create_mandate(world, world.partner, world.client_id)
    await world.partner.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": NOW.isoformat(),
            "note": "Teaser walk-through",
            "links": [
                {"record_type": "contact", "record_id": contact_id},
                {"record_type": "mandate", "record_id": mandate["id"]},
            ],
        },
        headers=world.partner.headers,
    )
    for body, visibility, extra in (
        ("Only mine", "private", {}),
        ("Deal remark", "deal_confidential", {"mandate_id": mandate["id"]}),
    ):
        created = await world.partner.client.post(
            "/api/v1/notes/",
            json={"record_type": "contact", "record_id": contact_id, "body": body, "visibility": visibility, **extra},
            headers=world.partner.headers,
        )
        assert created.status_code == 201, created.text
    own = await world.compliance.client.post(
        "/api/v1/notes/",
        json={"record_type": "contact", "record_id": contact_id, "body": "My own aside", "visibility": "private"},
        headers=world.compliance.headers,
    )
    assert own.status_code == 201, own.text

    response = await world.compliance.client.get(f"/api/v1/contacts/{contact_id}/export")

    assert response.status_code == 200, response.text
    document = json.loads(response.text)
    bodies = {note["body"] for note in document["notes"]}
    assert bodies == {"Deal remark", "My own aside"}
    deal_note = next(note for note in document["notes"] if note["body"] == "Deal remark")
    assert deal_note["mandate"] == "Falcon"
    assert "mandate_id" not in deal_note
    mandate_links = [link for link in document["activities"][0]["links"] if link["record_type"] == "mandate"]
    assert mandate_links == [{"record_type": "mandate", "code_name": "Falcon"}]
    assert "Acme" not in response.text
