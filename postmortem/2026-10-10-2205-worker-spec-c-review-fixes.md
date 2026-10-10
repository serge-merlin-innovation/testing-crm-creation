# Postmortem: spec review C fixes (resumed worker)

- Date: 2026-10-10 22:05
- Role: worker
- Task: Finish AUD-01 c1 and NFR-04 c4 from a killed worker, then NFR-02 c1, NFR-04 c2/c3, X-3 and the decision-report updates
- Model: Claude (jcode)

## Summary

Resumed a fixer that a server restart had killed. Checked the uncommitted AUD-01 c1 and NFR-04 c4 diff, fixed one ruff E501 and committed each finding on its own. Then added a reusable load-test workflow that also runs on PRs touching backend src, an AST check that every mutating route reaches an audit call, a compliance a11y identity with a PAGE_AUDIENCE coverage test, and the decision-report edits. Backend 1364/1365 passed, and the one failure (the NFR-02 perf test) passed when rerun alone. Ruff, mypy, vitest 464, tsc and eslint were clean. The first e2e run had one dashboard race, which I fixed. The full run then passed 71/71.

## Findings

### 1. Timing tests fail under host load

- Category: Automated checks
- Severity: medium
- Evidence: `test_nfr02_on_200k_contacts` failed in the full `-n 6` run at a load average of about 46, with other worktrees running pytest at the same time. It passed alone in 23 s. The targeted suite took 36 min for 624 tests.
- Suggested change: Mark the perf test `@pytest.mark.perf` and exclude it from the default `-n` run, or have it skip when `os.getloadavg()[0]` exceeds the CPU count. Run it serially in its own step.
- Target: apps/backend/tests/integration/performance/test_nfr02_performance.py, pyproject.toml markers

### 2. E2E clicks a save and moves on without waiting for the response

- Category: Coding standards
- Severity: medium
- Evidence: reports.e2e.ts asserted the input value, which was already filled locally, after "Update forecast" and then went to /analytics before the PUT landed. It failed only in the full run.
- Suggested change: Add a reviewer rule: after a mutating click, an e2e awaits `waitForResponse` (or a server-rendered result), never only the value the user typed.
- Target: docs/agents/CONSTITUTION.md, or the e2e section of the review skill

### 3. The e2e DB env is easy to forget

- Category: Information access
- Severity: low
- Evidence: A rerun without the POSTGRES_PORT/POSTGRES_DB exports failed at webServer startup with a bare TimeoutError. Nothing pointed to the missing DB settings.
- Suggested change: playwright.config could fail fast with a clear message when POSTGRES_PORT is unset or is 5432.
- Target: apps/frontend/playwright.config.ts

## Worker postmortems

none
