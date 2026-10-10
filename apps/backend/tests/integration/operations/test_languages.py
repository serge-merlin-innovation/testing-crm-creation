"""NFR-04 c1 end to end: errors, notifications and emails reach the user in their language."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.email import InMemoryEmailSender, set_email_sender
from src.interfaces.main import app
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.admin = await built.actor("admin", RoleName.ADMIN)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    yield built
    for session in built.clients:
        await session.aclose()
    set_clock(SystemClock())


async def set_language(actor, language):
    response = await actor.client.patch(f"/api/v1/users/{actor.id}", json={"language": language}, headers=actor.headers)
    assert response.status_code == 200, response.text
    assert response.json()["language"] == language


class TestErrors:
    async def test_a_domain_error_is_in_the_users_language(self, world):
        await set_language(world.analyst, "fr")
        response = await world.analyst.client.get("/api/v1/mandates/999999")
        assert response.status_code == 404
        response = await world.analyst.client.post(
            "/api/v1/tasks/",
            json={"title": "x", "due_date": "2026-10-20", "assignee_id": 999999},
            headers=world.analyst.headers,
        )
        assert response.json()["detail"] == "Destinataire inconnu"

    async def test_a_permission_error_is_in_dutch(self, world):
        await set_language(world.analyst, "nl")
        response = await world.analyst.client.get("/api/v1/users/")
        assert response.status_code == 403
        assert response.json()["detail"] == "U hebt geen toestemming voor deze actie."

    async def test_the_lang_cookie_applies_before_sign_in(self, client):
        client.cookies.set("lang", "fr")
        response = await client.post("/api/v1/auth/login", data={"email": "nobody@firm.be", "password": "wrong-password-1"})
        assert response.status_code == 401
        assert "mot de passe" in response.json()["detail"].lower()

    async def test_validation_errors_are_translated(self, client):
        response = await client.post("/api/v1/auth/password/forgot", json={}, headers={"Accept-Language": "nl-BE,nl;q=0.9"})
        assert response.status_code in (403, 422)
        if response.status_code == 422:
            assert response.json()["detail"] == "Ongeldige aanvraag. Controleer uw invoer en probeer opnieuw."

    async def test_english_stays_english(self, world):
        response = await world.analyst.client.get("/api/v1/users/")
        assert response.json()["detail"] == "You don't have permission for this action."


class TestNotificationsAndEmails:
    async def test_a_deal_notification_is_in_the_recipients_language(self, world):
        await set_language(world.analyst, "nl")
        client_id = await world.company("Acme Holding")
        mandate = await create_mandate(world, world.partner, client_id)
        response = await world.partner.client.post(
            f"/api/v1/mandates/{mandate['id']}/team",
            json={"user_id": world.analyst.id, "role": "analyst"},
            headers=world.partner.headers,
        )
        assert response.status_code in (200, 201), response.text
        inbox = (await world.analyst.client.get("/api/v1/notifications/")).json()
        assert inbox[0]["title"] == "U werd toegevoegd aan het dealteam van Falcon"
        dutch = [email for email in world.emails.sent if email.to == world.analyst.email]
        assert dutch[0].subject == "U werd toegevoegd aan het dealteam van Falcon"

    async def test_account_emails_follow_the_users_language(self, world):
        emails = InMemoryEmailSender()
        set_email_sender(emails)
        await set_language(world.analyst, "fr")
        anonymous = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        world.clients.append(anonymous)
        response = await anonymous.post("/api/v1/auth/password/forgot", json={"email": world.analyst.email})
        assert response.status_code == 202
        sent = emails.to(world.analyst.email)
        assert sent[0].subject == "Réinitialisez votre mot de passe CRM"
        assert "Choisissez un nouveau mot de passe" in sent[0].body
