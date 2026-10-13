# Postmortem: ticket #14 offers, templates, process letters, funnel, client report

- Date: 2026-10-10 14:21
- Role: worker
- Task: Implement issue #14 (BUY-05/06/07, ADM-07, REP-05, CON-01 c3, GDPR-01 c2, DEAL-03 c1)
- Model: Claude (Jcode worker)

## Summary

I built a new `process` module: versioned offers with a bid comparison sorted by EV with implied EV/EBITDA, bid deadlines and late flags, per-language templates with an audit trail and a fixed set of merge fields, process letters that apply the NDA, opt-out and Do not contact exclusions, a funnel with a PDF export, and a client status report PDF. I added migration 846f5d7b5c39 and four new deal-page tabs plus a `/templates` admin page. There are 19 integration tests, one per AC plus edge cases. The deal access matrix and the public API matrix got rows for the new routes. A process e2e spec was added. I merged #12 mid-run and re-pointed the migration. The final state is 1039 backend tests passing and 52/52 e2e passing.

## Findings

### 1. A fresh e2e database has no admin, and nothing says so

- Category: Information access
- Severity: medium
- Evidence: the first full Playwright run on a throwaway Postgres failed all of `accounts.setup.ts` with "Invalid email or password". The DB had migrations but no user. Passing FIRST_ADMIN_* env to the backend did not help. Only `uv run python -m scripts.setup_initial_data` seeded the admin. That cost two e2e runs.
- Suggested change: make the backend webServer command in `playwright.config.ts` run `scripts.setup_initial_data` before `fastapi run`, or add the step to the e2e note in the notes and README.
- Target: apps/frontend/playwright.config.ts

### 2. Two hand-maintained deal access matrices

- Category: Automated checks
- Severity: medium
- Evidence: I added rows to `test_deal_access_matrix.py`. The full run then failed `test_public_api.py`, which reuses the same ENDPOINTS but formats paths with its own kwargs (`document_id` missing) and only accepts 404/403 for non-OK statuses.
- Suggested change: move the path-format context (ids) into a shared helper in `deal_helpers.py`, used by both tests, so a new path placeholder is only added once.
- Target: apps/backend/tests/integration/crm/deal_helpers.py

### 3. alembic autogenerate output fails the repo's ruff config

- Category: Automated checks
- Severity: low
- Evidence: the generated migration used `typing.Union` and spurious `create_unique_constraint(None, 'roles'/'user')` ops. I only caught them at final lint.
- Suggested change: add ruff as an alembic `post_write_hooks` (format and `check --fix`) in alembic.ini, and fix the model or metadata drift behind the phantom unique constraints so `alembic check` is clean.
- Target: apps/backend/alembic.ini

### 4. The e2e ports were hard-coded and shared by parallel worktrees

- Category: Tool economy
- Severity: low
- Evidence: the brief warned that 3100/8100 could be busy because of #12 and #17. I made the ports overridable with `E2E_FRONTEND_PORT` / `E2E_BACKEND_PORT` and used 3114/8114, so I did not have to wait.
- Suggested change: document the env vars in the notes and frontend README so other workers use them rather than waiting.
- Target: apps/frontend/README.md

## Worker postmortems

none
