# Postmortem: ticket #9 conflict check and KYC gate

- Date: 2026-10-10 10:02
- Role: worker
- Task: Implement issue #9 (AUTHZ-05, DEAL-01 c2/c4, ORI-05) on feat/ma-crm
- Model: Claude (Jcode)

## Summary

Built a `compliance` module (counterparties, conflict reviews and hits, KYC records). It runs a group-aware, pg_trgm/unaccent conflict check on mandate creation and on each new counterparty, hides deals in review from everyone but the creator and compliance, and wires `set_kyc_check` into the Preparation gate. It also adds the sanctions freeze and an hourly job for the 5-working-day reminders and KYC refresh tasks. The frontend got a Compliance tab and a /conflict-reviews page. Alembic migration 4969f590271f is the single head. 17 new integration tests, 633 backend tests, 212 unit tests and 28 Playwright tests pass. Typecheck and lint are clean.

## Findings

### 1. Playwright silently ran a stale production build

- Category: Automated checks
- Severity: medium
- Evidence: the e2e config starts `pnpm start` on the existing `.next` build. A frontend change made after `pnpm build` was not exercised, which cost a debugging round.
- Suggested change: make `test:e2e` run `pnpm build` first, or have the webServer command build before it starts.
- Target: apps/frontend/package.json (`test:e2e`) or apps/frontend/playwright.config.ts

### 2. Error handler swallows domain messages unless the class is listed twice

- Category: Coding standards
- Severity: medium
- Evidence: the new `DealFrozenError` had a user-facing mapping in `EXCEPTION_MAPPING`, but the response was still the generic message. The handler only passes the detail for classes in a hard-coded tuple, so a second edit was needed.
- Suggested change: add a `user_facing` marker on DomainError subclasses (or a set next to EXCEPTION_MAPPING) and test that every mapped 403/409 error keeps its detail.
- Target: apps/backend/src/modules/common/utils/error_handler.py

### 3. Alembic autogenerate adds bogus unique constraints

- Category: Automated checks
- Severity: low
- Evidence: autogenerate emits `create_unique_constraint(None, 'roles'/'user', ['id'])` on every run, and I removed it by hand.
- Suggested change: drop the redundant `unique=True` from the primary-key `id` on Role and User, or filter it out in env.py `include_object`.
- Target: apps/backend/src/modules/role/models.py, apps/backend/migrations/env.py

### 4. Belgian companies need an enterprise number, and the notes did not say so

- Category: Navigation
- Severity: low
- Evidence: the e2e seed failed with 422 when it used country BE. Earlier tickets had quietly used NL.
- Suggested change: add a shared e2e helper for creating companies (the note is now in ~/.jcode-notes).
- Target: apps/frontend/tests/e2e/identities.ts

## Worker postmortems

none
