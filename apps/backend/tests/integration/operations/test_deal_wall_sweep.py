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
from tests.integration.crm.deal_helpers import build_world, create_mandate, seed_buyers
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
CODE_NAME = "Falcon"
# Company records are not deal data: a company's own name shows on its own record and in search, and
# the audit log records the company's creation. There only the code name proves a leak.
COMPANY_READS = {"/api/v1/companies/", "/api/v1/search/", "/api/v1/audit/"}
# Back-office reads every deal's fees, and compliance the audit log, by design.
SEES_THE_DEAL = {
    "/api/v1/reports/fee-forecast": {"compliance"},
    "/api/v1/reports/fee-forecast/export": {"compliance"},
    "/api/v1/fees/": {"compliance"},
    "/api/v1/fees/export": {"compliance"},
    "/api/v1/audit/": {"compliance"},
}
# Reads keyed by a record the deal touches rather than by the deal itself.
RECORD_READS = (
    "/api/v1/search/?q=Quorvant",
    "/api/v1/search/?q=Zephyrion",
    "/api/v1/timeline/company/{client_id}",
    "/api/v1/timeline/company/{target_id}",
    "/api/v1/timeline/contact/{contact_id}",
    "/api/v1/contacts/{contact_id}/buyer-roles",
    "/api/v1/contacts/{contact_id}/interactions",
    "/api/v1/companies/{buyer_company_id}/investor-profile",
)
QUERIES = {
    "/api/v1/search/": "?q=Falcon",
    "/api/v1/audit/": "?items_per_page=500",
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
    lead = built.lead
    buyers = await seed_buyers(built, lead, mandate["id"])
    contact = await lead.client.post(
        "/api/v1/contacts/",
        json={"first_name": "Jan", "last_name": "Peeters", "email": "jan@zephyrion.be", "source": "Forum"},
        headers=lead.headers,
    )
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["id"]
    linked = await lead.client.patch(
        f"/api/v1/mandates/{mandate['id']}/buyers/{buyers['buyer_id']}",
        json={"contact_id": contact_id},
        headers=lead.headers,
    )
    assert linked.status_code == 200, linked.text
    activity = await lead.client.post(
        "/api/v1/activities/",
        json={
            "type": "meeting",
            "occurred_at": "2026-10-13T09:00:00Z",
            "note": f"{CODE_NAME} kick-off with {CLIENT_NAME}",
            "links": [
                {"record_type": "mandate", "record_id": mandate["id"]},
                {"record_type": "contact", "record_id": contact_id},
                {"record_type": "company", "record_id": client_id},
            ],
        },
        headers=lead.headers,
    )
    assert activity.status_code == 201, activity.text
    task = await lead.client.post(
        "/api/v1/tasks/",
        json={
            "title": f"Call {CLIENT_NAME}",
            "assignee_id": lead.id,
            "due_date": "2026-10-16",
            "record_type": "mandate",
            "record_id": mandate["id"],
        },
        headers=lead.headers,
    )
    assert task.status_code == 201, task.text
    listed = (await lead.client.get(f"/api/v1/mandates/{mandate['id']}/buyers", headers=lead.headers)).json()
    built.record_ids = {
        "client_id": client_id,
        "target_id": target_id,
        "contact_id": contact_id,
        "buyer_company_id": listed["buyers"][0]["company_id"],
    }
    built.unstaffed = {key: await built.actor(key, role) for key, role in UNSTAFFED.items()}
    yield built
    await built.close()
    set_clock(SystemClock())


def secrets_for(path: str, persona: str) -> tuple[str, ...]:
    base = path.split("?", 1)[0]
    if path == f"/api/v1/search/?q={CODE_NAME}":
        # Search echoes the query; the empty deal list is the proof.
        return ()
    if persona in SEES_THE_DEAL.get(base, set()):
        return ()
    if base in COMPANY_READS:
        return (CODE_NAME,)
    return (CODE_NAME, CLIENT_NAME, TARGET_NAME)


async def sweep(world, persona: str, session: AsyncClient, headers: dict[str, str] | None = None) -> list[str]:
    leaks = []
    paths = [path + (QUERIES.get(path) or "") for path in collection_reads()]
    record_reads = {path.format(**world.record_ids) for path in RECORD_READS}
    paths += sorted(record_reads)
    for path in paths:
        limiter.reset()
        response = await session.get(path, headers=headers or {})
        body = response.content.decode("utf-8", errors="ignore")
        if path.startswith("/api/v1/search/") and response.status_code == 200 and response.json()["deals"]:
            leaks.append(f"{path} lists a deal")
        if path in record_reads and not (response.status_code < 300 or response.status_code in (403, 404)):
            leaks.append(f"{path} answered {response.status_code}")
        for name in secrets_for(path, persona):
            if name in body:
                leaks.append(f"{path} ({response.status_code}) names {name}")
    return leaks


async def test_no_collection_read_names_the_deal_to_an_unstaffed_user(world):
    leaks = []
    for key, actor in world.unstaffed.items():
        leaks += [f"{key}: {leak}" for leak in await sweep(world, key, actor.client, step_up(actor.email, actor.headers))]
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
            f"{key} (API): {leak}"
            for leak in await sweep(world, key, bearer, {"Authorization": f"Bearer {created.json()['token']}"})
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
        assert CODE_NAME not in ics.text


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
