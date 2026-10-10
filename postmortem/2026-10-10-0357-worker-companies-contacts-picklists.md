# Postmortem: companies, contacts and picklists (#5)

- Date: 2026-10-10 03:57
- Role: worker
- Task: Implement issue #5 backend slice (CO-01..03, CON-01, ADM-06, GDPR-01)
- Model: Claude

## Summary

Built picklist, company and contact modules with KBO/BCE and NBB ports, a migration and 24 integration tests plus unit tests. Full backend suite (195) green, mypy and ruff clean. Committed; feat/ma-crm was already merged in.

## Findings

### 1. Global 422 handler hid field errors, blocking "inline error" criteria

- Category: Information access
- Severity: medium
- Evidence: Tests asserting the invalid field failed because RequestValidationError and DomainError handlers return only a generic message; had to add a sanitized `errors: [{field, message}]` list.
- Suggested change: Document the 422 error shape (now `errors[]`) next to the error handler and in the frontend API client notes, so UI tickets render inline errors without rediscovering it.
- Target: docs/agents notes or `apps/backend/src/modules/common/utils/error_handler.py` docstring

### 2. Parallel tickets each autogenerate a migration off the same head

- Category: Automated checks
- Severity: medium
- Evidence: Migration c3d4e5f6a7b8 revises b7c1d2e3f4a5; ticket #2 runs in parallel and likely does the same, producing two Alembic heads on merge.
- Suggested change: Add a test asserting `alembic heads` returns exactly one head, so a merge with branching migrations fails CI.
- Target: apps/backend/tests/integration/foundation/test_migration.py

### 3. Autogenerate emits spurious unique constraints on roles/user id

- Category: Automated checks
- Severity: low
- Evidence: `alembic revision --autogenerate` added `create_unique_constraint(None, 'roles'|'user', ['id'])` from `unique=True` on primary keys; removed by hand.
- Suggested change: Drop `unique=True` from the primary keys in role/user models (or note it), so autogenerate is clean.
- Target: apps/backend/src/modules/{role,user}/models.py

## Worker postmortems

none
