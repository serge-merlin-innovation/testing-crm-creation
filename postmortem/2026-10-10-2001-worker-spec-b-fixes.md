# Postmortem: spec review B fixes (F1-F10, D36)

- Date: 2026-10-10 20:01
- Role: worker
- Task: Fix spec-traceability findings F1-F10 and D36 for Epics 4-7 on feat/ma-crm-spec-b, test first, one commit per finding.
- Model: Claude (jcode)

## Summary

Restored the 12 Epic 7 buyer statuses (with a data migration), made logged activities reset the buyer idle clock, sent dormant-prospect tasks to the strongest relationship holder, added EV/EBITDA and stake filters to Suggest buyers, and made the search ticket filter match investor ticket ranges. Also proved the conflict wall holds in global search and that Do not contact applies to letters and buyer PATCH, guarded portfolio links against overwriting a parent, and built the company detail page (KBO pre-fill, NBB financials with override and currency, parent picker and group tree) and the contact edit page with employment history and duplicate links. Every finding started with a red test, and the 5 new e2e tests were shown red against the old UI. Final state: Playwright 73/73 on a fresh throwaway DB, vitest 483, tsc and eslint clean, ruff and mypy clean, single alembic head 5ad009d4882d. Decision rows D35, D36, D37 and D53 are marked superseded.

## Findings

### 1. No way to fake KBO/NBB in a running backend

- Category: Information access
- Severity: medium
- Evidence: CO-01 c1 and CO-02 c2 had API tests only through `app.dependency_overrides`. An e2e test of the pre-fill UI needed a new test hook (`PUT /test-hooks/registers`) and a module-level setter in `company/dependencies.py`.
- Suggested change: Keep the hook. Note in the notes file that external register ports are faked via `/test-hooks/registers` in e2e, so the next UI ticket reuses it.
- Target: ~/.jcode-notes/ma-crm/notes.md

### 2. The i18n coverage test fails late and in the full suite only

- Category: Automated checks
- Severity: low
- Evidence: Two new user-facing backend strings (portfolio parent guard, fake NBB message) failed `test_i18n_coverage.py` only during the 28-minute full run.
- Suggested change: Run `tests/unit/infrastructure/test_i18n_coverage.py` in a fast pre-commit hook on backend changes.
- Target: .husky/pre-commit

### 3. NFR-02 perf test flakes under combined load

- Category: Automated checks
- Severity: low
- Evidence: `test_nfr02_on_200k_contacts` failed in the -n 6 run while Playwright ran in parallel, then passed alone (45 s).
- Suggested change: Mark it `serial` or run it in its own job, so a timing budget is not judged on a loaded machine.
- Target: apps/backend/tests/integration/performance/test_nfr02_performance.py

### 4. Similar-name duplicate check trips e2e fixtures

- Category: Coding standards
- Severity: low
- Evidence: "Employer One RUN" and "Employer Two RUN" were flagged as similar names. The test failed until the names were made distinct.
- Suggested change: Add a `uniqueCompanyName()` helper to tests/e2e/identities.ts that uses a random distinctive word per company, next to `runId()`.
- Target: apps/frontend/tests/e2e/identities.ts

### 5. Red-check by stashing is fragile

- Category: Tool economy
- Severity: low
- Evidence: Showing the new e2e tests red meant stashing tracked files and moving untracked `[id]` dirs by hand. One mv collided on two dirs with the same `[id]` name.
- Suggested change: Do red checks with `git worktree add` at the parent commit plus the test file, not by stashing in place.
- Target: docs/agents (testing workflow note)

## Worker postmortems

none
