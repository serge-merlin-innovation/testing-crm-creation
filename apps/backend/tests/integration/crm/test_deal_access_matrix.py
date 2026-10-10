"""The deal-access matrix (AUTHZ-02 c6).

Every endpoint under /api/v1/mandates, and every endpoint that resolves a deal through the
deal-access policy, must have a row in ENDPOINTS. `test_every_deal_scoped_endpoint_is_in_the_matrix`
fails the build when a new one is added without a row, so no deal endpoint ships untested.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI

from src.interfaces.main import app
from src.modules.mandate.policy import ReadGrant
from src.modules.mandate.policy import served_routes as served_routes_of
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world, create_mandate

pytestmark = pytest.mark.asyncio

OK = "ok"
HIDDEN = 404
FORBIDDEN = 403

# Who is asking. "member" is an analyst staffed on the deal; everyone else is not staffed.
PERSONAS = {
    "member": RoleName.ANALYST,
    "lead": RoleName.PARTNER,
    "other_partner": RoleName.PARTNER,
    "director": RoleName.DIRECTOR,
    "admin": RoleName.ADMIN,
    "compliance": RoleName.COMPLIANCE,
    "read_only": RoleName.READ_ONLY,
}
UNSTAFFED = ("other_partner", "director", "admin", "compliance", "read_only")


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    # {persona: expected}; OK means a 2xx whose body does not leak the deal to the unstaffed.
    expected: dict[str, Any]
    body: Callable[[dict], dict] | None = None
    # For collection endpoints: an unstaffed caller gets 200 but must not see the deal.
    collection: bool = False


def hidden_from_unstaffed(**staffed: Any) -> dict[str, Any]:
    return {**{persona: HIDDEN for persona in UNSTAFFED}, **staffed}


ENDPOINTS: list[Endpoint] = [
    Endpoint("GET", "/api/v1/mandates/", {persona: OK for persona in PERSONAS}, collection=True),
    Endpoint("GET", "/api/v1/notifications/", {persona: OK for persona in PERSONAS}, collection=True),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint(
        "PATCH",
        "/api/v1/mandates/{mandate_id}",
        hidden_from_unstaffed(member=OK, lead=OK),
        body=lambda ctx: {"version": ctx["version"](), "estimated_ev": "26000"},
    ),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/history", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/team", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/team/candidates", hidden_from_unstaffed(member=FORBIDDEN, lead=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/team",
        hidden_from_unstaffed(member=FORBIDDEN, lead=OK),
        body=lambda ctx: {"user_id": ctx["spare_user_id"], "role": "analyst"},
    ),
    Endpoint(
        "DELETE",
        "/api/v1/mandates/{mandate_id}/team/{user_id}",
        hidden_from_unstaffed(member=FORBIDDEN, lead=OK),
    ),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/wall-crossings", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/links", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/links",
        hidden_from_unstaffed(member=OK, lead=OK),
        body=lambda ctx: {"label": "IM", "url": "https://files.example.com/im.pdf"},
    ),
    Endpoint("DELETE", "/api/v1/mandates/{mandate_id}/links/{link_id}", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/stage",
        hidden_from_unstaffed(member=OK, lead=OK),
        body=lambda ctx: {"version": ctx["version"](), "stage": "conflict_review"},
    ),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/close",
        hidden_from_unstaffed(member=FORBIDDEN, lead=OK),
        body=lambda ctx: {"version": ctx["version"](), "outcome": "aborted", "abort_reason": "Seller withdrew"},
    ),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/reopen",
        hidden_from_unstaffed(member=FORBIDDEN, lead=422),
        body=lambda ctx: {"version": ctx["version"](), "reason": "Back on"},
    ),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/milestones", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/milestones",
        hidden_from_unstaffed(member=OK, lead=OK),
        body=lambda ctx: {"name": "IM sent", "planned_date": "2026-11-01"},
    ),
    Endpoint(
        "PATCH",
        "/api/v1/mandates/{mandate_id}/milestones/{milestone_id}",
        hidden_from_unstaffed(member=OK, lead=OK),
        body=lambda ctx: {"actual_date": "2026-11-02"},
    ),
    Endpoint("DELETE", "/api/v1/mandates/{mandate_id}/milestones/{milestone_id}", hidden_from_unstaffed(member=OK, lead=OK)),
    # Read-only summary: back-office (compliance persona) reads it unstaffed (ROLE-01 c4).
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/summary", hidden_from_unstaffed(member=OK, lead=OK, compliance=OK)),
    # Fee fields (AUTHZ-06): the analyst member is refused, back-office reads every deal's fees.
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/fees", hidden_from_unstaffed(member=FORBIDDEN, lead=OK, compliance=OK)),
    Endpoint(
        "PUT",
        "/api/v1/mandates/{mandate_id}/fees",
        hidden_from_unstaffed(member=FORBIDDEN, lead=OK, compliance=OK),
        body=lambda ctx: {"success_fee_kind": "percent", "success_fee_percent": "2"},
    ),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/invoices", hidden_from_unstaffed(member=FORBIDDEN, lead=OK, compliance=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/invoices",
        hidden_from_unstaffed(member=FORBIDDEN, lead=FORBIDDEN, compliance=OK),
        body=lambda ctx: {"type": "retainer", "amount": "10000", "sent_date": "2026-10-01"},
    ),
    Endpoint(
        "PATCH",
        "/api/v1/mandates/{mandate_id}/invoices/{invoice_id}",
        hidden_from_unstaffed(member=FORBIDDEN, lead=FORBIDDEN, compliance=OK),
        body=lambda ctx: {"paid_date": "2026-10-05"},
    ),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/counterparties", hidden_from_unstaffed(member=OK, lead=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/counterparties",
        hidden_from_unstaffed(member=OK, lead=OK),
        body=lambda ctx: {"company_id": ctx["company_id"]},
    ),
    # Compliance-only: the team sees the deal (403), nobody else learns it exists (404). The matrix deal has
    # no conflict and is not frozen, so compliance's decision and unfreeze are refused on their merits (422).
    Endpoint(
        "GET", "/api/v1/mandates/{mandate_id}/conflicts", hidden_from_unstaffed(member=FORBIDDEN, lead=FORBIDDEN, compliance=OK)
    ),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/conflicts/decision",
        hidden_from_unstaffed(member=FORBIDDEN, lead=FORBIDDEN, compliance=422),
        body=lambda ctx: {"decision": "clear", "reason": "No overlap"},
    ),
    Endpoint("GET", "/api/v1/mandates/{mandate_id}/kyc", hidden_from_unstaffed(member=OK, lead=OK, compliance=OK)),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/kyc",
        hidden_from_unstaffed(member=FORBIDDEN, lead=FORBIDDEN, compliance=OK),
        body=lambda ctx: {"ubo_check": True, "id_check": True, "pep_sanctions_screening": True},
    ),
    Endpoint(
        "POST",
        "/api/v1/mandates/{mandate_id}/unfreeze",
        hidden_from_unstaffed(member=FORBIDDEN, lead=FORBIDDEN, compliance=422),
        body=lambda ctx: {"reason": "Cleared"},
    ),
]

# Under /mandates but about no existing deal: creating one, and picking its lead partner.
NOT_DEAL_SCOPED = {
    ("POST", "/api/v1/mandates/"),
    ("GET", "/api/v1/mandates/lead-partners"),
    ("GET", "/api/v1/mandates/filters"),
}


def served_routes() -> set[tuple[str, str]]:
    return {
        (route.method, route.path)
        for route in served_routes_of(app.routes)
        if route.path.startswith("/api/v1/mandates") or route.deal_scoped
    }


async def test_every_deal_scoped_endpoint_is_in_the_matrix():
    assert served_routes(), "No deal routes found: the route walk is broken"
    registered = {(endpoint.method, endpoint.path) for endpoint in ENDPOINTS}
    missing = served_routes() - registered - NOT_DEAL_SCOPED
    assert not missing, f"Deal-scoped endpoints without a row in the access matrix: {sorted(missing)}"
    stale = registered - served_routes() - {("GET", "/api/v1/notifications/")}
    assert not stale, f"Matrix rows for endpoints that no longer exist: {sorted(stale)}"


async def test_the_guard_flags_a_new_unregistered_deal_endpoint():
    stray = APIRouter()

    @stray.get("/api/v1/deal-export/{mandate_id}")
    async def export(grant: ReadGrant) -> dict:
        return {}

    probe = FastAPI()
    probe.include_router(stray)
    flagged = {(r.method, r.path) for r in served_routes_of(probe.routes) if r.deal_scoped}
    assert ("GET", "/api/v1/deal-export/{mandate_id}") in flagged
    assert flagged - {(e.method, e.path) for e in ENDPOINTS}


async def test_every_endpoint_with_a_mandate_id_goes_through_the_policy():
    unguarded = [
        (route.method, route.path)
        for route in served_routes_of(app.routes)
        if "{mandate_id}" in route.path and not route.deal_scoped
    ]
    assert not unguarded, f"These read a deal without the deal-access policy: {unguarded}"


@pytest.fixture
async def world(client, seeded_db):
    built = await build_world(seeded_db)
    built.people = {key: await built.actor(key, role) for key, role in PERSONAS.items()}
    built.client_id = await built.company("Acme Holding")
    yield built
    await built.close()


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: f"{e.method} {e.path}")
@pytest.mark.parametrize("persona", list(PERSONAS))
async def test_deal_access_matrix(world, endpoint: Endpoint, persona: str):
    lead = world.people["lead"]
    mandate = await create_mandate(world, lead, world.client_id)
    mandate_id = mandate["id"]
    member = world.people["member"]
    response = await lead.client.post(
        f"/api/v1/mandates/{mandate_id}/team", json={"user_id": member.id, "role": "analyst"}, headers=lead.headers
    )
    assert response.status_code == 201
    spare = await world.actor("spare", RoleName.ANALYST)
    victim = await world.actor("victim", RoleName.ANALYST)
    await lead.client.post(
        f"/api/v1/mandates/{mandate_id}/team", json={"user_id": victim.id, "role": "analyst"}, headers=lead.headers
    )
    link = await lead.client.post(
        f"/api/v1/mandates/{mandate_id}/links",
        json={"label": "VDR", "url": "https://vdr.example.com/falcon"},
        headers=lead.headers,
    )

    milestone = await lead.client.post(
        f"/api/v1/mandates/{mandate_id}/milestones", json={"name": "Teaser", "planned_date": "2026-11-01"}, headers=lead.headers
    )
    invoice = await world.people["compliance"].client.post(
        f"/api/v1/mandates/{mandate_id}/invoices",
        json={"type": "retainer", "amount": "5000", "sent_date": "2026-09-01"},
        headers=world.people["compliance"].headers,
    )
    assert invoice.status_code == 201, invoice.text

    async def current_version() -> int:
        return (await lead.client.get(f"/api/v1/mandates/{mandate_id}", headers=lead.headers)).json()["version"]

    version = await current_version()
    context = {"version": lambda: version, "spare_user_id": spare.id, "company_id": world.client_id}
    path = endpoint.path.format(
        mandate_id=mandate_id,
        user_id=victim.id,
        link_id=link.json()["id"],
        milestone_id=milestone.json()["id"],
        invoice_id=invoice.json()["id"],
    )
    caller = world.people[persona]
    response = await caller.client.request(
        endpoint.method,
        path,
        json=endpoint.body(context) if endpoint.body else None,
        headers=caller.headers,
    )

    expected = endpoint.expected[persona]
    if expected == OK:
        assert 200 <= response.status_code < 300, response.text
        if endpoint.collection and persona in UNSTAFFED:
            assert "Falcon" not in response.text, response.text
            assert "Acme" not in response.text, response.text
    else:
        assert response.status_code == expected, response.text
        assert "Falcon" not in response.text
        assert "Acme" not in response.text
