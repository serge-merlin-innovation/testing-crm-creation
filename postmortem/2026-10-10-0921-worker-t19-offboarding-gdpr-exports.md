# Postmortem: ticket #19 offboarding, GDPR, export controls

- Date: 2026-10-10 09:21
- Role: worker
- Task: Implement #19 (AUTH-05, ADM-03, GDPR-02/03, REP-06), plus the #4 account pages and #2 admin security screens
- Model: Claude (Jcode)

## Summary

Built three backend slices (offboarding, privacy, data_export) with one alembic-generated migration, 19 integration tests mapped to the ACs, and the frontend pages (accept-invitation, reset-password, users admin, privacy, exports) with unit and Playwright coverage. Merged the feat/ma-crm tip (ticket #8), re-chained the migration to keep one head, and ran 591 backend tests, 215 unit tests and 31/31 E2E on a throwaway Postgres.

## Findings

### 1. The E2E ports are shared by every worktree

- Category: Automated checks
- Severity: medium
- Evidence: `playwright.config.ts` fixes 8100/3100 with `reuseExistingServer: false`. The #16 worker's suite held 8100, so my run aborted with "already used", and I had to poll until the ports were free.
- Suggested change: Read the ports from env (`E2E_BACKEND_PORT`, `E2E_FRONTEND_PORT`) with the current defaults, and document per-worktree ports in the notes so parallel workers don't collide.
- Target: apps/frontend/playwright.config.ts

### 2. Migrations that read data break the offline-mode test

- Category: Navigation
- Severity: medium
- Evidence: My first grant step used `bind.execute(select...)`. It passed online upgrade/downgrade but failed `test_offline_migration_accepts_percent_encoded_database_url`, and I only found out from the full suite.
- Suggested change: Add a one-line pointer next to the migration conventions: "migrations must be offline-safe: write data changes as literal SQL, never read rows".
- Target: docs/agents/CONSTITUTION.md (or the migrations README)

### 3. Seeding roles never updates existing ones, so new permissions need a migration

- Category: Navigation
- Severity: low
- Evidence: Adding `privacy.manage`/`exports.approve` to `DEFAULT_ROLES` only reaches fresh installs. Existing roles needed a grant in the migration. I learned this from a comment in permissions.py, not from any guide.
- Suggested change: Add a note in permissions.py next to `Permission`: "a new permission granted by default also needs a migration grant for existing roles".
- Target: apps/backend/src/modules/role/permissions.py

### 4. `test.use({ storageState })` leaks into `browser.newContext()`

- Category: Coding standards
- Severity: low
- Evidence: Two E2E tests failed with CSRF 403 inside `inviteUser`, because the admin cookies from the describe-level `storageState` rode along on the invitee context.
- Suggested change: Make `inviteUser` create its context with an explicit empty `storageState` so it can't inherit cookies.
- Target: apps/frontend/tests/e2e/identities.ts

## Worker postmortems

none
