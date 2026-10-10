# Postmortem: spec review A fixes (Epics 0-3)

- Date: 2026-10-10 20:30
- Role: worker
- Task: Fix the 8 non-OK findings and 4 decision rows from review-spec-a.md, test first, one commit per finding
- Model: Claude (jcode)

## Summary

The session fixed all eight findings, plus the D16/D17/D42/D8 rows and the retag, in 15 commits. The full Playwright suite passed 71/71 on a throwaway Postgres (:55731, ports 3231/8231). Fixing D16 (repeat clients now flagged) broke fixtures that reused one client for every deal: two backend tests and one e2e spec, all found only by running the suites. The other costs came from long feedback loops: the crm integration subset took 18 minutes, and a server reload killed the full pytest run once.

## Findings

### 1. Shared fixtures silently depend on conflict-check semantics

- Category: Automated checks
- Severity: medium
- Evidence: After D16, `test_pipeline.py::test_filters_return_only_accessible_deals`, `test_reporting.py::deal()` and `reports.e2e.ts` failed. Each created several deals for one client company, which is now a potential conflict that hides the deal.
- Suggested change: Have `deal_helpers.create_mandate` default to a fresh client company per call unless `client_id` is passed. Give e2e a `freshClient()` helper next to `runId()`.
- Target: apps/backend/tests/integration/crm/deal_helpers.py, apps/frontend/tests/e2e/identities.ts

### 2. Integration subsets are slow to iterate on

- Category: Tool economy
- Severity: medium
- Evidence: `pytest tests/integration/crm -n 6` took 18 min and exceeded the 10 min foreground cap twice, so the run had to go to the background and be awaited.
- Suggested change: Document in notes a quick loop: run only the touched files with `-n 6`, and leave the full tier for the final run.
- Target: ~/.jcode-notes/ma-crm/notes.md

### 3. APP_URL was not set in production infra

- Category: Information access
- Severity: medium
- Evidence: The login Origin check compares against `settings.APP_URL`, but `backend-container-app.bicepparam` set only FRONTEND_BASE_URL (unused). Invitation and calendar links were already built from the default localhost URL.
- Suggested change: Add a test in test_hosting_contract.py that every setting used for links or origins is set in the bicepparam.
- Target: apps/backend/tests/unit/.../test_hosting_contract.py

### 4. The unsaved-changes registry had no producers

- Category: Coding standards
- Severity: low
- Evidence: `unsavedChanges.mark` was never called, so the AUTH-04 c4 dialog was dead code, and unit tests covered only the store.
- Suggested change: Reviewer rule: a registry or hook added for a criterion needs at least one real caller covered by e2e.
- Target: docs/agents/CONSTITUTION.md (reviewer judgement)

## Worker postmortems

none
