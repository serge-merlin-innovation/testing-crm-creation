"""NFR-02 on the full 200k-contact dataset, measured in-process against a real Postgres.

c1: searches answer in under 1 s and page data in under 2 s (the 95th percentile of repeated calls).
c2: a report over all deals answers in under 10 s.
The 50-concurrent-user part is the k6 run in `perf/k6/load.js` (CI job `load-test`).
"""

import statistics
import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from scripts.load_dataset import seed_load_dataset
from src.interfaces.main import app
from src.modules.api_access.rate_limit import limiter
from src.modules.picklist.service import seed_default_picklists

pytestmark = [pytest.mark.asyncio, pytest.mark.performance]

SEARCH_BUDGET = 1.0
PAGE_BUDGET = 2.0
REPORT_BUDGET = 10.0
REPEATS = 10

SEARCHES = [
    "/api/v1/contacts/?q=peeters&limit=25",
    "/api/v1/contacts/?q=claire.maes&limit=25",
    "/api/v1/companies/?q=brabant&limit=25",
    "/api/v1/search/?q=hainaut",
    "/api/v1/search/?q=dubois",
]
PAGES = [
    "/api/v1/mandates/",
    "/api/v1/tasks/mine",
    "/api/v1/notifications/",
    "/api/v1/reports/home",
    "/api/v1/users/me",
]
# Every report that covers all of a user's deals. Add a row when a new firm-wide report ships.
ALL_DEAL_REPORTS = [
    "/api/v1/mandates/",
    "/api/v1/reports/dashboard",
    "/api/v1/reports/win-loss?from=2020-01-01&to=2030-12-31",
    "/api/v1/reports/fee-forecast",
    "/api/v1/reports/fee-forecast/export",
]


@pytest.fixture
async def loaded(client, seeded_db):
    await seed_default_picklists(seeded_db)
    # One partner staffed on every deal, so "all deals" really is all 2,000 for the report.
    dataset = await seed_load_dataset(seeded_db, deals=2_000, team_size=6, tag="perf")
    partner_id = dataset.user_ids[0]
    await seeded_db.execute(
        text(
            "INSERT INTO deal_team_members (mandate_id, user_id, role, added_by, added_at) "
            "SELECT id, :user_id, 'partner', lead_partner_id, now() FROM mandates m WHERE NOT EXISTS "
            "(SELECT 1 FROM deal_team_members t WHERE t.mandate_id = m.id AND t.user_id = :user_id)"
        ),
        {"user_id": partner_id},
    )
    await seeded_db.commit()
    session = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {dataset.tokens[partner_id]}"},
        timeout=60,
    )
    yield dataset, session
    await session.aclose()


async def timed(session: AsyncClient, path: str) -> float:
    # The 100/min API-token cap is not what is measured here.
    limiter.reset()
    started = time.perf_counter()
    response = await session.get(path)
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, f"{path}: {response.status_code} {response.text[:300]}"
    return elapsed


def p95(samples: list[float]) -> float:
    return statistics.quantiles(samples, n=20)[-1] if len(samples) > 1 else samples[0]


async def test_nfr02_on_200k_contacts(loaded):
    """One seeded database (seeding 200k rows per test would dominate the suite), every budget checked."""
    dataset, session = loaded
    assert dataset.contacts == 200_000
    assert len(dataset.user_ids) == 50
    hits = (await session.get("/api/v1/contacts/?q=peeters&limit=25")).json()
    assert len(hits) == 25, "the search must hit real rows, or its timing proves nothing"
    deals = (await session.get("/api/v1/mandates/")).json()
    assert len(deals) >= 2_000
    slow = []
    for paths, budget in ((SEARCHES, SEARCH_BUDGET), (PAGES, PAGE_BUDGET)):
        for path in paths:
            await timed(session, path)
            samples = [await timed(session, path) for _ in range(REPEATS)]
            print(f"NFR-02 {path} p95={p95(samples):.3f}s")  # noqa: T201
            if p95(samples) >= budget:
                slow.append(f"{path} p95 {p95(samples):.3f}s >= {budget}s")
    for path in ALL_DEAL_REPORTS:
        elapsed = await timed(session, path)
        print(f"NFR-02 report {path} {elapsed:.3f}s")  # noqa: T201
        if elapsed >= REPORT_BUDGET:
            slow.append(f"{path} took {elapsed:.2f}s >= {REPORT_BUDGET}s")
    assert not slow, "\n".join(slow)
