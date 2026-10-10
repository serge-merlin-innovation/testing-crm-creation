"""Cross-cutting (derived): a non-staffed user never receives a deal's target or client name.

The access matrix (crm/test_deal_access_matrix.py) proves every deal-scoped route answers 404/403.
This sweep covers the rest: every collection, search, export, report, notification and calendar
read the app serves, called by every unstaffed role through the browser session and the public
API, must not contain the deal's client or target name. A new list endpoint is swept automatically.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.interfaces.main import app
from src.modules.api_access.rate_limit import limiter
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate
from tests.integration.foundation.helpers import step_up

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
CLIENT_NAME = "Quorvant Holding"
TARGET_NAME = "Zephyrion Werken"
UNSTAFFED = {
    "other_partner": RoleName.PARTNER,
    "director": RoleName.DIRECTOR,
    "analyst": RoleName.ANALYST,
    "admin": RoleName.ADMIN,
    "compliance": RoleName.COMPLIANCE,
    "read_only": RoleName.READ_ONLY,
}
# Company records are not deal data: a company's own name shows on its own record, and the audit
# log (audit.read) records the company's creation. What must never appear is the deal tying them
# together; the audit sweep below checks that separately.
NOT_DEAL_READS = {"/api/v1/companies/", "/api/v1/search/", "/api/v1/audit/"}
QUERIES = {
    "/api/v1/search/": "?q=Falcon",
    "/api/v1/reports/win-loss": "?from=2020-01-01&to=2030-12-31",
    "/api/v1/exports/contacts": "?q=",
    "/api/v1/auth/invitations": None,
    "/api/v1/test-hooks/emails": None,
}


def collection_reads() -> list[str]:
    paths = set()
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        for candidate in contexts() if contexts else []:
            if "GET" in (candidate.methods or set()) and "{" not in candidate.path and candidate.path.startswith("/api/v1/"):
                paths.add(candidate.path)
    return sorted(path for path in paths if QUERIES.get(path, "") is not None)


@pytest.fixture
async def world(client, seeded_db):
    set_clock(FrozenClock(NOW))
    built = await build_world(seeded_db)
    built.lead = await built.actor("lead", RoleName.PARTNER)
    client_id = await built.company(CLIENT_NAME, "other")
    target_id = await built.company(TARGET_NAME, "target")
    mandate = await create_mandate(built, built.lead, client_id, target_id=target_id)
    milestone = await built.lead.client.post(
        f"/api/v1/mandates/{mandate['id']}/milestones",
        json={"name": "Signing", "planned_date": "2026-11-01"},
        headers=built.lead.headers,
    )
    assert milestone.status_code == 201, milestone.text
    built.unstaffed = {key: await built.actor(key, role) for key, role in UNSTAFFED.items()}
    yield built
    await built.close()
    set_clock(SystemClock())


async def sweep(session: AsyncClient, headers: dict[str, str] | None = None) -> list[str]:
    leaks = []
    for path in collection_reads():
        limiter.reset()
        response = await session.get(path + QUERIES.get(path, ""), headers=headers or {})
        body = response.text
        if path in NOT_DEAL_READS:
            continue
        for name in (CLIENT_NAME, TARGET_NAME):
            if name in body:
                leaks.append(f"{path} ({response.status_code}) names {name}")
    return leaks


async def test_no_collection_read_names_the_deal_to_an_unstaffed_user(world):
    leaks = []
    for key, actor in world.unstaffed.items():
        leaks += [f"{key}: {leak}" for leak in await sweep(actor.client, step_up(actor.email, actor.headers))]
    assert not leaks, "\n".join(leaks)


async def test_nor_over_the_public_api(world):
    leaks = []
    for key, actor in world.unstaffed.items():
        created = await actor.client.post(
            "/api/v1/api-tokens/", json={"name": "sweep"}, headers=step_up(actor.email, actor.headers)
        )
        assert created.status_code == 201, created.text
        bearer = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        world.clients.append(bearer)
        leaks += [
            f"{key} (API): {leak}" for leak in await sweep(bearer, {"Authorization": f"Bearer {created.json()['token']}"})
        ]
    assert not leaks, "\n".join(leaks)


async def test_the_calendar_feed_of_an_unstaffed_user_omits_the_deal(world):
    for key, actor in world.unstaffed.items():
        response = await actor.client.get("/api/v1/calendar-feed/")
        if key == "read_only":
            # Read-only has no record access, so no feed at all (ROLE-01 c3).
            assert response.status_code == 403
            continue
        feed = response.json()
        ics = await actor.client.get("/api/v1/calendar-feed/ics/" + feed["url"].rsplit("/", 1)[-1])
        assert ics.status_code == 200
        assert CLIENT_NAME not in ics.text
        assert TARGET_NAME not in ics.text
        assert "Falcon" not in ics.text


async def test_the_names_exist_to_leak(world):
    # The sweep only proves something if the names are in the system: the staffed lead reads them
    # on the deal itself, the one place they belong (and the access matrix guards).
    deals = (await world.lead.client.get("/api/v1/mandates/")).json()
    detail = (await world.lead.client.get(f"/api/v1/mandates/{deals[0]['id']}")).text
    assert CLIENT_NAME in detail
    assert TARGET_NAME in detail
    assert len(collection_reads()) > 40


async def test_audit_rows_about_the_deal_never_carry_a_company_name(world):
    for key in ("admin", "compliance"):
        actor = world.unstaffed[key]
        rows = (await actor.client.get("/api/v1/audit/?record_type=mandate")).json()
        assert rows, "the deal's own audit rows are listed"
        for row in rows:
            text = str(row)
            assert CLIENT_NAME not in text
            assert TARGET_NAME not in text
