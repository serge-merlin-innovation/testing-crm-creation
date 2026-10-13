# Postmortem: #16 search, relationship holders, merge, Excel import

- Date: 2026-10-10 09:15
- Role: worker
- Task: Implement GitHub issue #16 (CON-02 c1, CON-03, CON-04, CON-05) on feat/ma-crm-t16
- Model: Claude (Jcode)

## Summary

Built three backend modules (search, merge, data_import) plus relationship holders on contacts, an Alembic migration generated with `alembic revision --autogenerate` and extended with the pg_trgm/unaccent DDL, three frontend pages and an e2e spec. 21 new integration tests (one or more per AC, including a 100k-row timing test), 593 backend tests, 213 unit tests and 34/34 Playwright passed after merging the feat/ma-crm tip (#8) and rechaining the migration onto its head. Not pushed.

## Findings

### 1. Merge reference list is a hand-maintained registry with no guard

- Category: Automated checks
- Severity: high
- Evidence: `merge/service.py` lists every column pointing at contacts/companies (`REFERENCES`). A later ticket that adds a FK or a polymorphic `record_type/record_id` to these tables will silently leave rows on the deleted duplicate, or make merge fail on a RESTRICT FK.
- Suggested change: a unit test that walks `Base.metadata` for every ForeignKey to `contacts.id`/`companies.id` and every table with `record_type`+`record_id` columns, and fails when one is missing from `REFERENCES` (same idea as the deal-access matrix test).
- Target: apps/backend/tests/unit/modules/ (new test)

### 2. Shared e2e ports between parallel worktrees

- Category: Information access
- Severity: medium
- Evidence: Playwright refused to start because the #19 worktree's backend held 8100; only `lsof` revealed it was another worker. Parallel tickets will keep colliding.
- Suggested change: let `playwright.config.ts` read `E2E_FRONTEND_PORT`/`E2E_BACKEND_PORT` from the environment (defaults unchanged), and note in the swarm notes to pick a per-worktree pair.
- Target: apps/frontend/playwright.config.ts

### 3. Domain-error messages are swallowed into a generic one

- Category: Navigation
- Severity: low
- Evidence: the mapped `MergeBlockedError` message rendered as "Something went wrong" until rethrown as HTTPException in the route; the rule lived only in agent notes.
- Suggested change: a one-line docstring in `modules/common/constants.py` above the mapping saying user-facing 4xx text must be raised from the route.
- Target: apps/backend/src/modules/common/constants.py

### 4. `alembic check` reports pre-existing drift

- Category: Automated checks
- Severity: low
- Evidence: autogenerate keeps proposing `create_unique_constraint(None, 'roles'|'user', ['id'])`, which had to be stripped by hand from the new migration.
- Suggested change: align the `user`/`roles` models with the schema (drop the redundant `unique=True` on primary keys or add the constraint), then wire `alembic check` into CI on a throwaway Postgres.
- Target: apps/backend/src/modules/user/models.py, CI workflow

## Worker postmortems

none
