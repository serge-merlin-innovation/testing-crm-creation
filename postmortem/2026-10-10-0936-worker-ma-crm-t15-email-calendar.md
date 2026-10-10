# Postmortem: ticket #15 email logging and calendar feed

- Date: 2026-10-10 09:36
- Role: worker
- Task: Implement issue #15 (ACT-04, ACT-05, CON-02 c2, AUTHZ-02 c3) on feat/ma-crm-t15
- Model: Claude (Jcode)

## Summary

I wrote 13 failing integration tests first, then added two backend modules (`email_logging`, `calendar_feed`), an Alembic migration (f140753b1423), profile cards, an `/inbox` page, a "Who knows" panel on contacts and a Playwright spec. Backend: 579 tests pass, ruff and mypy are clean. Frontend: tsc, eslint and 209 vitest tests pass. Playwright: 29/29 on a throwaway Postgres on port 55451. After merging the feat/ma-crm tip there is still a single head. Nothing was pushed.

## Findings

### 1. The settings/.env.example coupling showed up only in the full suite

- Category: Navigation
- Severity: low
- Evidence: adding two `config(...)` settings failed `test_env_example_documents_every_configurable_setting`. I only found out after the 4-minute full run.
- Suggested change: add a one-line comment above the settings classes: "every config() key must appear in .env.example (test_settings enforces this)".
- Target: apps/backend/src/infrastructure/config/settings.py

### 2. An accessible name on a row button broke an unrelated e2e locator

- Category: Coding standards
- Severity: low
- Evidence: an `aria-label` that held the contact's name made `getByRole("cell", {name})` in crm-records.e2e.ts match two cells. Only the full e2e run caught it.
- Suggested change: add a reviewer note. Row action buttons use visible text and row-scoped locators. They do not use aria-labels that repeat the row's data.
- Target: docs/agents/CONSTITUTION.md (reviewer judgement)

### 3. Autogenerate adds spurious unique constraints

- Category: Automated checks
- Severity: medium
- Evidence: `alembic revision --autogenerate` emitted `create_unique_constraint(None, 'roles'/'user', ['id'])`, which I removed by hand. A later worker could commit it without noticing.
- Suggested change: fix the model drift on `roles.id` and `user.id`, or filter these in `env.py` `include_object`. Add a test that runs autogenerate against head and expects an empty diff.
- Target: apps/backend/migrations/env.py

### 4. Prettier is not runnable in the frontend

- Category: Automated checks
- Severity: low
- Evidence: `pnpm prettier --check` gave "Command prettier not found". Formatting is not checked locally.
- Suggested change: either add prettier to the frontend's devDependencies and its lint script, or state that eslint owns formatting.
- Target: apps/frontend/package.json

## Worker postmortems

none
