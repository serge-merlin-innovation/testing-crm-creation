# Postmortem: ticket #17 reporting slice

- Date: 2026-10-10 15:06
- Role: worker
- Task: Home page, firm dashboard, fee forecast + Excel, win/loss report, AUTHZ-02 c4 and Read-only lockdown
- Model: Claude (jcode)

## Summary

Built module `reporting` (deal_forecasts migration 87dc941ce57c on 846f5d7b5c39), four report endpoints, a deal forecast endpoint, a router-level Read-only guard, four frontend pages and an e2e spec. Merged the #14 tip midway (one conflict in the router list). Final: pytest 1072 passed, vitest 253, tsc/eslint/ruff/mypy clean, Playwright 58/58 on a fresh DB (ports 3177/8177, Postgres :55517).

## Findings

### 1. Module wiring rule only surfaced in the full suite

- Category: Automated checks
- Severity: medium
- Evidence: `test_module_wiring` (needs crud.py and dependencies.py in every module) failed only after the 11-minute full run. I had run only the targeted integration tests.
- Suggested change: Name the required module files in the module-slice section of CONSTITUTION.md, or run `tests/unit` in a pre-commit hook. The unit tier takes seconds.
- Target: docs/agents/CONSTITUTION.md, .husky/pre-commit

### 2. E2E button names collide through non-exact matching

- Category: Coding standards
- Severity: medium
- Evidence: deals.e2e uses `getByRole("button", { name: "Save" })` without exact matching. My new "Save forecast" button on the summary tab broke an unrelated spec.
- Suggested change: Add an ESLint rule (or a reviewer rule) that requires `exact: true` on short role names in e2e specs.
- Target: apps/frontend/eslint.config, docs/agents/CONSTITUTION.md

### 3. Venv lacked a dependency added by the merged ticket

- Category: Automated checks
- Severity: low
- Evidence: After merging #14, test_process failed with ImportError pypdf until I ran `uv sync --extra dev`. Plain `uv sync --all-groups` does not install the dev extra the tests need.
- Suggested change: Add a `test` script that runs `uv sync --extra dev` before pytest, or move the dev tools to a dependency group.
- Target: apps/backend/pyproject.toml, apps/backend/package.json

### 4. E2E assertions assumed an empty database

- Category: Coding standards
- Severity: low
- Evidence: Three reports.e2e assertions failed on a full run because earlier specs had already seeded deals and quarter totals (count "1", fee "250000.00").
- Suggested change: Add a note to the e2e README that the specs share one DB, so assertions should be relative to the API or scoped to the RUN id.
- Target: apps/frontend/tests/e2e (README or identities.ts header)

## Worker postmortems

none
