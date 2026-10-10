"""Ticket #15: ACT-04 email logging, ACT-05 calendar feed, CON-02 c2 interactions, AUTHZ-02 c3."""

import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.config.settings import settings
from src.modules.email_logging.models import LoggedEmail, LoggingAddress, UnmatchedEmail
from src.modules.mandate.models import Mandate
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
SECRET = "inbound-test-secret"


@pytest.fixture
async def world(client, seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_EMAIL_SECRET", SECRET)
    clock = FrozenClock(NOW)
    set_clock(clock)
    built = await build_world(seeded_db)
    built.anon = client
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.client_id = await built.company("Acme Holding")
    built.target_id = await built.company("Secret Target NV")
    contact = await built.partner.client.post(
        "/api/v1/contacts/",
        json={"first_name": "Jan", "last_name": "Peeters", "email": "jan@acme.be", "source": "Forum"},
        headers=built.partner.headers,
    )
    built.contact_id = contact.json()["id"]
    other = await built.partner.client.post(
        "/api/v1/contacts/",
        json={"first_name": "Eva", "last_name": "Claes", "email": "Eva@Bank.be", "source": "Forum"},
        headers=built.partner.headers,
    )
    built.other_contact_id = other.json()["id"]
    built.mandate = await create_mandate(built, built.partner, built.client_id, target_id=built.target_id)
    yield built
    await built.close()
    set_clock(SystemClock())


async def address_of(actor):
    response = await actor.client.get("/api/v1/email-logging/address", headers=actor.headers)
    assert response.status_code == 200, response.text
    return response.json()["address"]


async def inbound(world, **email):
    payload = {
        "subject": "Hello",
        "text": "Body",
        "to": [],
        "cc": [],
        "bcc": [],
        "attachments": [],
        "spf": "pass",
        "dkim": "pass",
        **email,
    }
    return await world.anon.post("/api/v1/email-logging/inbound", json=payload, headers={"X-Inbound-Secret": SECRET})


async def timeline(actor, record_type, record_id):
    response = await actor.client.get(f"/api/v1/timeline/{record_type}/{record_id}", headers=actor.headers)
    assert response.status_code == 200, response.text
    return response.json()["activities"]


# ACT-04 c1: BCC
async def test_bcc_email_is_logged_on_every_matched_contact_timeline(world):
    address = await address_of(world.partner)
    response = await inbound(
        world,
        sender="Paula <paula@firm.be>",
        to=["jan@acme.be"],
        cc=["eva@bank.be", "anna@firm.be"],
        bcc=[address],
        subject="Next steps",
        text="See you Monday",
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "logged"
    for contact_id in (world.contact_id, world.other_contact_id):
        [activity] = await timeline(world.analyst, "contact", contact_id)
        assert activity["type"] == "email"
        assert activity["author_id"] == world.partner.id
        assert "Next steps" in activity["note"]


# ACT-04 c1: forward, the original correspondents are read from the forwarded header block
async def test_forwarded_email_matches_the_original_correspondents(world):
    address = await address_of(world.partner)
    response = await inbound(
        world,
        sender="paula@firm.be",
        to=[address],
        subject="Fwd: Offer",
        text=(
            "FYI\n\n---------- Forwarded message ---------\n"
            "From: Jan Peeters <jan@acme.be>\nTo: paula@firm.be\n\nOffer attached"
        ),
    )
    assert response.json()["status"] == "logged"
    assert len(await timeline(world.partner, "contact", world.contact_id)) == 1


# ACT-04 c2
async def test_email_from_an_address_not_linked_to_a_crm_user_is_rejected(world):
    address = await address_of(world.partner)
    response = await inbound(world, sender="spoof@evil.com", to=["jan@acme.be"], bcc=[address])
    assert response.status_code == 403
    assert await timeline(world.partner, "contact", world.contact_id) == []
    assert (await world.db.execute(select(UnmatchedEmail))).first() is None


# Security review S13: a forged From is refused unless the provider verified SPF and DKIM.
@pytest.mark.parametrize(("spf", "dkim"), [("fail", "pass"), ("pass", "fail"), ("softfail", "none"), (None, None)])
async def test_email_without_passing_spf_and_dkim_is_rejected(world, spf, dkim):
    address = await address_of(world.partner)
    response = await inbound(world, sender="paula@firm.be", to=["jan@acme.be"], bcc=[address], spf=spf, dkim=dkim)
    assert response.status_code == 403
    assert await timeline(world.partner, "contact", world.contact_id) == []


async def test_logging_address_token_has_128_bits(world):
    address = await address_of(world.partner)
    token = address.split("@")[0].removeprefix("log-")
    assert len(token) == 32
    int(token, 16)


async def test_inbound_webhook_needs_the_provider_secret(world):
    address = await address_of(world.partner)
    response = await world.anon.post(
        "/api/v1/email-logging/inbound",
        json={"sender": "paula@firm.be", "to": ["jan@acme.be"], "bcc": [address], "subject": "x", "text": "y"},
        headers={"X-Inbound-Secret": "wrong"},
    )
    assert response.status_code == 401


# ACT-04 c3
async def test_unmatched_email_lands_in_my_unmatched_inbox_to_link_or_discard(world):
    address = await address_of(world.partner)
    first = await inbound(world, sender="paula@firm.be", to=["stranger@nowhere.be"], bcc=[address], subject="Intro")
    second = await inbound(world, sender="paula@firm.be", to=["other@nowhere.be"], bcc=[address], subject="Spam")
    assert first.json()["status"] == second.json()["status"] == "unmatched"

    inbox = await world.partner.client.get("/api/v1/email-logging/unmatched", headers=world.partner.headers)
    assert [item["subject"] for item in inbox.json()] == ["Spam", "Intro"]
    other_inbox = await world.analyst.client.get("/api/v1/email-logging/unmatched", headers=world.analyst.headers)
    assert other_inbox.json() == []
    intro, spam = inbox.json()[1], inbox.json()[0]

    stolen = await world.analyst.client.post(
        f"/api/v1/email-logging/unmatched/{intro['id']}/link",
        json={"links": [{"record_type": "contact", "record_id": world.contact_id}]},
        headers=world.analyst.headers,
    )
    assert stolen.status_code == 404
    linked = await world.partner.client.post(
        f"/api/v1/email-logging/unmatched/{intro['id']}/link",
        json={"links": [{"record_type": "contact", "record_id": world.contact_id}]},
        headers=world.partner.headers,
    )
    assert linked.status_code == 201, linked.text
    assert [a["id"] for a in await timeline(world.partner, "contact", world.contact_id)] == [linked.json()["id"]]

    discarded = await world.partner.client.delete(
        f"/api/v1/email-logging/unmatched/{spam['id']}", headers=world.partner.headers
    )
    assert discarded.status_code == 204
    after = await world.partner.client.get("/api/v1/email-logging/unmatched", headers=world.partner.headers)
    assert after.json() == []


# ACT-04 c4
async def test_code_name_in_subject_links_the_deal_only_when_i_am_staffed(world):
    partner_address = await address_of(world.partner)
    outsider_address = await address_of(world.outsider)
    staffed = await inbound(
        world, sender="paula@firm.be", to=["jan@acme.be"], bcc=[partner_address], subject="[falcon] Draft IM"
    )
    unstaffed = await inbound(
        world, sender="otto@firm.be", to=["jan@acme.be"], bcc=[outsider_address], subject="[Falcon] Fishing"
    )
    assert staffed.json()["status"] == unstaffed.json()["status"] == "logged"
    deal_items = await timeline(world.partner, "mandate", world.mandate["id"])
    assert [a["id"] for a in deal_items] == [staffed.json()["activity_id"]]
    outsider_items = await timeline(world.outsider, "contact", world.contact_id)
    assert [a["id"] for a in outsider_items] == [unstaffed.json()["activity_id"]]
    assert outsider_items[0]["links"] == [{"record_type": "contact", "record_id": world.contact_id}]


# ACT-04 c5
async def test_only_attachment_names_are_stored_never_the_files(world):
    address = await address_of(world.partner)
    content = base64.b64encode(b"TOP-SECRET-FILE-BYTES").decode()
    response = await inbound(
        world,
        sender="paula@firm.be",
        to=["jan@acme.be"],
        bcc=[address],
        attachments=[{"filename": "IM.pdf", "content": content}, {"filename": "Model.xlsx", "content": content}],
    )
    logged = (await world.db.execute(select(LoggedEmail))).scalar_one()
    assert logged.attachment_names == ["IM.pdf", "Model.xlsx"]
    [activity] = await timeline(world.partner, "contact", world.contact_id)
    assert "IM.pdf" in activity["note"]
    assert "Model.xlsx" in activity["note"]
    assert activity["id"] == response.json()["activity_id"]
    assert content not in activity["note"]
    assert "TOP-SECRET" not in activity["note"]
    columns = [getattr(logged, c.key) for c in LoggedEmail.__table__.columns]
    assert all(content not in str(value) for value in columns)


async def test_the_same_message_is_logged_once(world):
    address = await address_of(world.partner)
    for _ in range(2):
        await inbound(world, sender="paula@firm.be", to=["jan@acme.be"], bcc=[address], message_id="<m-1@firm.be>")
    assert len(await timeline(world.partner, "contact", world.contact_id)) == 1


# CON-02 c2
async def test_contact_shows_last_interaction_and_count_per_colleague(world):
    partner_address = await address_of(world.partner)
    analyst_address = await address_of(world.analyst)
    await inbound(world, sender="paula@firm.be", to=["jan@acme.be"], bcc=[partner_address], date="2026-09-01T10:00:00Z")
    await inbound(world, sender="paula@firm.be", to=["jan@acme.be"], bcc=[partner_address], date="2026-10-02T10:00:00Z")
    await inbound(world, sender="anna@firm.be", to=["jan@acme.be"], bcc=[analyst_address], date="2026-08-15T10:00:00Z")
    meeting = await world.analyst.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": "2026-09-20T14:00:00Z",
            "note": "Lunch",
            "links": [{"record_type": "contact", "record_id": world.contact_id}],
        },
        headers=world.analyst.headers,
    )
    assert meeting.status_code == 201
    response = await world.outsider.client.get(
        f"/api/v1/contacts/{world.contact_id}/interactions", headers=world.outsider.headers
    )
    assert response.status_code == 200, response.text
    rows = {row["user_id"]: row for row in response.json()}
    assert rows[world.partner.id]["count"] == 2
    assert rows[world.partner.id]["last_interaction_at"].startswith("2026-10-02")
    assert rows[world.analyst.id]["count"] == 2
    assert rows[world.analyst.id]["last_interaction_at"].startswith("2026-09-20")
    assert response.json()[0]["user_id"] == world.partner.id
    assert rows[world.partner.id]["name"]


# ACT-05 c1
async def test_calendar_feed_lists_my_meetings_tasks_and_milestones(world):
    await world.partner.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": "2026-10-12T14:00:00Z",
            "note": "Coffee with Jan",
            "links": [{"record_type": "contact", "record_id": world.contact_id}],
        },
        headers=world.partner.headers,
    )
    await world.partner.client.post(
        "/api/v1/tasks/",
        json={"title": "Send NDA", "assignee_id": world.partner.id, "due_date": "2026-10-15"},
        headers=world.partner.headers,
    )
    await world.partner.client.post(
        f"/api/v1/mandates/{world.mandate['id']}/milestones",
        json={"name": "IM sent", "planned_date": "2026-10-20"},
        headers=world.partner.headers,
    )
    feed = await world.partner.client.get("/api/v1/calendar-feed/", headers=world.partner.headers)
    assert feed.status_code == 200, feed.text
    url = feed.json()["url"]
    assert url.startswith(settings.APP_URL)
    assert url.endswith(".ics")

    ics = await world.anon.get(url.removeprefix(settings.APP_URL))
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    body = ics.text
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert body.rstrip().endswith("END:VCALENDAR")
    assert body.count("BEGIN:VEVENT") == 3
    assert "DTSTART:20261012T140000Z" in body
    assert "Send NDA" in body
    assert "DTSTART;VALUE=DATE:20261015" in body
    assert "DTSTART;VALUE=DATE:20261020" in body
    assert "Falcon" in body


# ACT-05 c2 and AUTHZ-02 c3
async def test_deal_events_and_non_staffed_references_show_only_the_code_name(world):
    await world.partner.client.post(
        f"/api/v1/mandates/{world.mandate['id']}/team",
        json={"user_id": world.analyst.id, "role": "analyst"},
        headers=world.partner.headers,
    )
    meeting = await world.analyst.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": "2026-10-13T09:00:00Z",
            "note": "Secret Target NV management meeting",
            "participants": ["CEO of Secret Target NV"],
            "links": [
                {"record_type": "mandate", "record_id": world.mandate["id"]},
                {"record_type": "company", "record_id": world.target_id},
            ],
        },
        headers=world.analyst.headers,
    )
    assert meeting.status_code == 201, meeting.text
    await world.partner.client.post(
        "/api/v1/tasks/",
        json={
            "title": "Call Secret Target NV",
            "assignee_id": world.analyst.id,
            "due_date": "2026-10-16",
            "record_type": "mandate",
            "record_id": world.mandate["id"],
        },
        headers=world.partner.headers,
    )
    await world.partner.client.post(
        f"/api/v1/mandates/{world.mandate['id']}/milestones",
        json={"name": "Secret Target NV site visit", "planned_date": "2026-10-21"},
        headers=world.partner.headers,
    )
    url = (await world.analyst.client.get("/api/v1/calendar-feed/", headers=world.analyst.headers)).json()["url"]
    path = url.removeprefix(settings.APP_URL)

    staffed = (await world.anon.get(path)).text
    assert staffed.count("BEGIN:VEVENT") == 3
    assert staffed.count("Falcon") >= 3
    assert "Secret Target" not in staffed
    assert "Acme" not in staffed

    removed = await world.partner.client.delete(
        f"/api/v1/mandates/{world.mandate['id']}/team/{world.analyst.id}", headers=world.partner.headers
    )
    assert removed.status_code == 204, removed.text
    unstaffed = (await world.anon.get(path)).text
    assert "Secret Target" not in unstaffed
    assert "Acme" not in unstaffed
    assert "Falcon" in unstaffed


# ACT-05 c3
async def test_regenerating_the_feed_url_kills_the_old_one(world):
    old = (await world.partner.client.get("/api/v1/calendar-feed/", headers=world.partner.headers)).json()["url"]
    again = (await world.partner.client.get("/api/v1/calendar-feed/", headers=world.partner.headers)).json()["url"]
    assert old == again
    regenerated = await world.partner.client.post("/api/v1/calendar-feed/regenerate", headers=world.partner.headers)
    assert regenerated.status_code == 200, regenerated.text
    new = regenerated.json()["url"]
    assert new != old
    assert (await world.anon.get(old.removeprefix(settings.APP_URL))).status_code == 404
    assert (await world.anon.get(new.removeprefix(settings.APP_URL))).status_code == 200


async def test_a_guessed_feed_token_is_not_found(world):
    assert (await world.anon.get("/api/v1/calendar-feed/ics/not-a-token.ics")).status_code == 404


# Review S3 (ROLE-01 c3): Read-only gets no logging address or feed, and a stale address logs nothing.
async def test_read_only_cannot_log_email_or_hold_a_feed(world):
    viewer = await world.actor("rita", RoleName.READ_ONLY)
    for method, path in (
        ("GET", "/api/v1/email-logging/address"),
        ("GET", "/api/v1/email-logging/unmatched"),
        ("DELETE", "/api/v1/email-logging/unmatched/1"),
        ("POST", "/api/v1/email-logging/unmatched/1/link"),
        ("GET", "/api/v1/calendar-feed/"),
        ("POST", "/api/v1/calendar-feed/regenerate"),
    ):
        response = await viewer.client.request(method, path, json={"links": []}, headers=viewer.headers)
        assert response.status_code == 403, (path, response.text)

    world.db.add(LoggingAddress(user_id=viewer.id, token="log-stale", created_at=NOW))
    await world.db.commit()
    stale = f"log-stale@{settings.INBOUND_EMAIL_DOMAIN}"
    response = await inbound(world, sender=viewer.email, to=["jan@acme.be"], bcc=[stale])
    assert response.status_code == 403, response.text
    assert await timeline(world.partner, "contact", world.contact_id) == []


# Review S15 (DEAL-01 c4): a deal sent back to conflict review or rejected leaves the team's feed entirely.
async def test_feed_drops_a_deal_hidden_by_conflict_review(world):
    await world.partner.client.post(
        f"/api/v1/mandates/{world.mandate['id']}/team",
        json={"user_id": world.analyst.id, "role": "analyst"},
        headers=world.partner.headers,
    )
    await world.partner.client.post(
        f"/api/v1/mandates/{world.mandate['id']}/milestones",
        json={"name": "Site visit", "planned_date": "2026-10-21"},
        headers=world.partner.headers,
    )
    await world.analyst.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": "2026-10-13T09:00:00Z",
            "note": "Kick-off",
            "links": [{"record_type": "mandate", "record_id": world.mandate["id"]}],
        },
        headers=world.analyst.headers,
    )
    url = (await world.analyst.client.get("/api/v1/calendar-feed/", headers=world.analyst.headers)).json()["url"]
    path = url.removeprefix(settings.APP_URL)
    assert (await world.anon.get(path)).text.count("Falcon") == 2

    mandate = await world.db.get(Mandate, world.mandate["id"])
    mandate.conflict_status = "rejected"
    await world.db.commit()

    hidden = (await world.anon.get(path)).text
    assert "Falcon" not in hidden
    assert "BEGIN:VEVENT" not in hidden


# The webhook is authenticated by its secret alone: a caller that happens to carry a session cookie
# (no CSRF header) is still accepted.
async def test_inbound_webhook_ignores_a_session_cookie(world):
    address = await address_of(world.partner)
    payload = {
        "subject": "Hello",
        "text": "Body",
        "to": ["jan@acme.be"],
        "cc": [],
        "bcc": [address],
        "attachments": [],
        "spf": "pass",
        "dkim": "pass",
    }
    response = await world.partner.client.post(
        "/api/v1/email-logging/inbound", json={"sender": world.partner.email, **payload}, headers={"X-Inbound-Secret": SECRET}
    )
    assert response.status_code == 202, response.text
