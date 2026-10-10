"""NFR-05: the public API for the data room, BI and future tools."""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.interfaces.main import app
from src.modules.api_access.rate_limit import limiter
from src.modules.audit.models import AuditEntry
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate
from tests.integration.crm.test_deal_access_matrix import ENDPOINTS, FORBIDDEN, HIDDEN, OK

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    clock = FrozenClock(NOW)
    set_clock(clock)
    limiter.reset()
    built = await build_world(seeded_db)
    built.clock = clock
    built.partner = await built.actor("paula", RoleName.PARTNER)
    built.analyst = await built.actor("anna", RoleName.ANALYST)
    built.outsider = await built.actor("otto", RoleName.PARTNER)
    built.client_id = await built.company("Acme Holding")
    built.api = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield built
    await built.api.aclose()
    await built.close()
    set_clock(SystemClock())
    limiter.reset()


async def issue_token(actor, name: str = "BI export") -> str:
    response = await actor.client.post("/api/v1/api-tokens/", json={"name": name}, headers=actor.headers)
    assert response.status_code == 201, response.text
    return response.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def staffed_mandate(world) -> dict:
    mandate = await create_mandate(world, world.partner, world.client_id)
    response = await world.partner.client.post(
        f"/api/v1/mandates/{mandate['id']}/team",
        json={"user_id": world.analyst.id, "role": "analyst"},
        headers=world.partner.headers,
    )
    assert response.status_code == 201
    return mandate


# AC1: OAuth 2.0 client credentials or personal API tokens; no basic auth or shared keys.


async def test_a_personal_token_issued_in_the_crm_authenticates_api_calls(world):
    token = await issue_token(world.partner)
    assert token.startswith("crm_pat_")

    response = await world.api.get("/api/v1/mandates/", headers=bearer(token))

    assert response.status_code == 200


async def test_the_token_secret_is_shown_once_and_only_its_prefix_is_listed(world):
    token = await issue_token(world.partner)

    listed = (await world.partner.client.get("/api/v1/api-tokens/", headers=world.partner.headers)).json()

    assert token not in str(listed)
    assert listed[0]["prefix"] == token[:12]


async def test_a_revoked_token_no_longer_works(world):
    token = await issue_token(world.partner)
    token_id = (await world.partner.client.get("/api/v1/api-tokens/", headers=world.partner.headers)).json()[0]["id"]

    response = await world.partner.client.delete(f"/api/v1/api-tokens/{token_id}", headers=world.partner.headers)
    assert response.status_code == 204

    assert (await world.api.get("/api/v1/mandates/", headers=bearer(token))).status_code == 401


async def test_an_unknown_token_is_rejected(world):
    assert (await world.api.get("/api/v1/mandates/", headers=bearer("crm_pat_forged"))).status_code == 401


async def test_basic_auth_is_refused_even_with_valid_credentials(world):
    basic = base64.b64encode(f"{world.partner.email}:Password123!".encode()).decode()

    response = await world.api.get("/api/v1/mandates/", headers={"Authorization": f"Basic {basic}"})

    assert response.status_code == 401
    assert "basic" in response.json()["detail"].lower()


async def test_a_token_cannot_mint_more_tokens(world):
    token = await issue_token(world.partner)

    response = await world.api.post("/api/v1/api-tokens/", json={"name": "child"}, headers=bearer(token))

    assert response.status_code == 403


async def test_oauth_client_credentials_issue_an_expiring_access_token(world):
    created = await world.partner.client.post("/api/v1/api-clients/", json={"name": "Data room"}, headers=world.partner.headers)
    assert created.status_code == 201, created.text
    credentials = created.json()

    granted = await world.api.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        },
    )
    assert granted.status_code == 200, granted.text
    body = granted.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600

    assert (await world.api.get("/api/v1/mandates/", headers=bearer(body["access_token"]))).status_code == 200

    world.clock.advance(timedelta(seconds=3601))
    assert (await world.api.get("/api/v1/mandates/", headers=bearer(body["access_token"]))).status_code == 401


async def test_oauth_rejects_a_wrong_secret_and_other_grants(world):
    credentials = (
        await world.partner.client.post("/api/v1/api-clients/", json={"name": "BI"}, headers=world.partner.headers)
    ).json()

    wrong = await world.api.post(
        "/api/v1/oauth/token",
        data={"grant_type": "client_credentials", "client_id": credentials["client_id"], "client_secret": "nope"},
    )
    password_grant = await world.api.post(
        "/api/v1/oauth/token",
        data={"grant_type": "password", "client_id": credentials["client_id"], "client_secret": "x"},
    )

    assert wrong.status_code == 401
    assert wrong.json()["error"] == "invalid_client"
    assert password_grant.status_code == 400
    assert password_grant.json()["error"] == "unsupported_grant_type"


async def test_a_deleted_client_can_no_longer_get_tokens(world):
    credentials = (
        await world.partner.client.post("/api/v1/api-clients/", json={"name": "BI"}, headers=world.partner.headers)
    ).json()
    response = await world.partner.client.delete(f"/api/v1/api-clients/{credentials['id']}", headers=world.partner.headers)
    assert response.status_code == 204

    granted = await world.api.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        },
    )
    assert granted.status_code == 401


# AC2: the same role and deal-team rules as in the UI (AUTHZ-01/02/06).


async def test_api_reads_follow_the_deal_team_rules(world):
    mandate = await staffed_mandate(world)
    member = await issue_token(world.analyst)
    outsider = await issue_token(world.outsider)

    assert (await world.api.get(f"/api/v1/mandates/{mandate['id']}", headers=bearer(member))).status_code == 200
    assert (await world.api.get(f"/api/v1/mandates/{mandate['id']}", headers=bearer(outsider))).status_code == 404
    listed = await world.api.get("/api/v1/mandates/", headers=bearer(outsider))
    assert "Falcon" not in listed.text


async def test_api_respects_role_permissions(world):
    token = await issue_token(world.analyst)

    response = await world.api.get("/api/v1/audit/", headers=bearer(token))

    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: f"{e.method} {e.path}")
async def test_deal_access_matrix_holds_over_api_tokens(world, endpoint):
    """Every deal-scoped endpoint gives an API token the same answer as the UI session."""
    mandate = await staffed_mandate(world)
    spare = await world.actor("spare", RoleName.ANALYST)
    link = await world.partner.client.post(
        f"/api/v1/mandates/{mandate['id']}/links",
        json={"label": "VDR", "url": "https://vdr.example.com/falcon"},
        headers=world.partner.headers,
    )
    milestone = await world.partner.client.post(
        f"/api/v1/mandates/{mandate['id']}/milestones",
        json={"name": "Teaser", "planned_date": "2026-11-01"},
        headers=world.partner.headers,
    )
    version = (await world.partner.client.get(f"/api/v1/mandates/{mandate['id']}", headers=world.partner.headers)).json()[
        "version"
    ]
    path = endpoint.path.format(
        mandate_id=mandate["id"], user_id=world.analyst.id, link_id=link.json()["id"], milestone_id=milestone.json()["id"]
    )
    context = {"version": lambda: version, "spare_user_id": spare.id, "company_id": world.client_id}

    for persona, actor in (("other_partner", world.outsider), ("member", world.analyst)):
        token = await issue_token(actor, f"{persona}-{endpoint.method}")
        response = await world.api.request(
            endpoint.method, path, json=endpoint.body(context) if endpoint.body else None, headers=bearer(token)
        )
        expected = endpoint.expected[persona]
        if expected == OK:
            assert 200 <= response.status_code < 300, (persona, response.text)
            if endpoint.collection and persona == "other_partner":
                assert "Falcon" not in response.text
        else:
            assert expected in (HIDDEN, FORBIDDEN)
            assert response.status_code == expected, (persona, response.text)
            assert "Falcon" not in response.text


# AC4: over 100 requests per minute -> 429 with Retry-After.


async def test_a_client_over_100_requests_a_minute_gets_429_with_retry_after(world):
    token = await issue_token(world.partner)

    for _ in range(100):
        assert (await world.api.get("/api/v1/notifications/", headers=bearer(token))).status_code == 200

    throttled = await world.api.get("/api/v1/notifications/", headers=bearer(token))
    assert throttled.status_code == 429
    assert 1 <= int(throttled.headers["Retry-After"]) <= 60

    world.clock.advance(timedelta(seconds=61))
    assert (await world.api.get("/api/v1/notifications/", headers=bearer(token))).status_code == 200


async def test_the_limit_is_per_client_not_shared(world):
    first = await issue_token(world.partner, "one")
    second = await issue_token(world.analyst, "two")
    for _ in range(100):
        await world.api.get("/api/v1/notifications/", headers=bearer(first))

    assert (await world.api.get("/api/v1/notifications/", headers=bearer(second))).status_code == 200


async def test_minting_new_oauth_tokens_does_not_reset_the_client_limit(world):
    credentials = (
        await world.partner.client.post("/api/v1/api-clients/", json={"name": "BI"}, headers=world.partner.headers)
    ).json()
    form = {
        "grant_type": "client_credentials",
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
    }
    first = (await world.api.post("/api/v1/oauth/token", data=form)).json()["access_token"]
    for _ in range(100):
        await world.api.get("/api/v1/notifications/", headers=bearer(first))
    second = (await world.api.post("/api/v1/oauth/token", data=form)).json()["access_token"]

    assert (await world.api.get("/api/v1/notifications/", headers=bearer(second))).status_code == 429


# AC6: API writes are audited like UI changes (AUD-01).


async def test_an_api_write_is_recorded_in_the_audit_log_like_a_ui_change(world):
    mandate = await staffed_mandate(world)
    token = await issue_token(world.analyst)

    response = await world.api.patch(
        f"/api/v1/mandates/{mandate['id']}",
        json={"version": mandate["version"], "estimated_ev": "30000"},
        headers={**bearer(token), "User-Agent": "bi-connector/1.0"},
    )
    assert response.status_code == 200, response.text

    entry = (
        (
            await world.db.execute(
                select(AuditEntry)
                .where(AuditEntry.record_type == "mandate", AuditEntry.record_id == str(mandate["id"]))
                .order_by(AuditEntry.id.desc())
            )
        )
        .scalars()
        .first()
    )
    assert entry is not None
    assert entry.user_id == world.analyst.id
    assert entry.user_agent == "bi-connector/1.0"


async def test_issuing_and_revoking_credentials_is_audited(world):
    await issue_token(world.partner)
    await world.partner.client.post("/api/v1/api-clients/", json={"name": "BI"}, headers=world.partner.headers)

    actions = set((await world.db.execute(select(AuditEntry.action).where(AuditEntry.user_id == world.partner.id))).scalars())

    assert {"api_token.issue", "api_client.create"} <= actions
