# NFR-02 load test (ticket #20)

## Setup

- Dataset: `uv run python -m scripts.seed_load_test` (`scripts/load_dataset.py`): 50 active users (10 Partners, 15 Directors, 20 Analysts, 3 Compliance, 2 Read-only), 200,000 contacts with an employment each, 20,000 companies, 2,000 running deals with 6-person teams, one personal API token per user.
- Load: `perf/k6/load.js`, 50 constant virtual users for 2 minutes, one user per token, about one request per second each (the API allows 100 per minute per token). Each iteration runs one search (contacts, global search or companies, random term) and one page load (deal list, deal detail, my tasks, notifications, home, me). Read-only users load the aggregated dashboard.
- Server: one `fastapi run` process (no workers) on a MacBook (Apple silicon) against Postgres 16 in Docker, the same machine also running k6 and other projects' containers. Production runs 0.25 vCPU per replica, so this is not a capacity prediction, only a regression gate.

## Results (2026-10-10, 2 minutes, 7,898 requests, 0.00% failed)

| Metric | p50 | p90 | p95 | p99 | Budget |
| --- | --- | --- | --- | --- | --- |
| Page loads (API behind each page) | 55 ms | 200 ms | 282 ms | 439 ms | p95 < 2,000 ms |
| Searches | 122 ms | 538 ms | 738 ms | 1,066 ms | p95 < 1,000 ms |

The first run measured search p95 1,217 ms. Contact search used `ILIKE '%term%'` on three columns (a sequential scan of 200k rows) and two extra queries per result row. It now matches on the folded expressions the trigram GIN indexes already cover and loads employments and relationship holders in one query each. Single-call contact search fell from about 130 ms to 30 ms.

## In-process budgets (pytest)

`tests/integration/performance/test_nfr02_performance.py` seeds the same dataset in the test Postgres and checks the p95 of 10 calls per endpoint plus every all-deal report. Measured: searches 20-130 ms (budget 1 s), pages 2-160 ms (budget 2 s), all-deal reports 8-110 ms for 2,000 deals (budget 10 s).

## Limits

- The page-load figure is the API time behind each page, not browser rendering. Next.js server rendering adds one relay hop per call.
- The CI job `load-test` repeats this on a GitHub runner on every release candidate; the production figure needs a run against staging once it exists.
