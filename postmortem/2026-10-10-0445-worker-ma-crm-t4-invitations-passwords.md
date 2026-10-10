# Postmortem: ticket #4 invitations and passwords

- Date: 2026-10-10 04:45
- Role: worker
- Task: Implement issue #4 (ADM-01, ADM-04, AUTH-08..11) on feat/ma-crm-t4 and merge feat/ma-crm + feat/ma-crm-t2 tips
- Model: Claude

## Summary

Wrote 24 AC tests first, built a `modules/account` slice (invite, CSV import, resend, accept with 2FA enrolment, policy, history, forgot/reset, change, list filters, CSV export, dormancy) plus an HIBP breach port and one migration. 250 then 380 backend tests passed after merging both tips. The merge exposed two migrations sharing revision `d4e5f6a7b8c9` (t2 login security and ma-crm mandates); I re-id'd t2's migration and chained mine after it to keep one head.

## Findings

### 1. Duplicate Alembic revision IDs across parallel branches are only caught at merge time

- Category: Automated checks
- Severity: high
- Evidence: After merging feat/ma-crm and feat/ma-crm-t2, `alembic heads` showed a duplicated `d4e5f6a7b8c9`. No test failed on it. The notes rule ("generate IDs with alembic revision") came after the fact.
- Suggested change: Add a unit test that parses `migrations/versions/*.py`, asserts unique `revision` values and exactly one head, and rejects IDs matching a sequential hex pattern like `[a-f0-9]` runs (`abcdef`-style). Runs in the pre-commit pytest.
- Target: apps/backend/tests/unit/infrastructure/test_migrations_graph.py

### 2. Module-wiring rules found only by running the full suite

- Category: Navigation
- Severity: low
- Evidence: `test_module_wiring.py` demanded crud.py/dependencies.py and indexed FKs, and `test_settings.py` demanded every setting in `.env.example`. I learned this on the first full run.
- Suggested change: Add a one-line pointer in the notes/CONTEXT for "new module checklist: required files, indexed FKs, new settings go in .env.example".
- Target: docs/agents/CONSTITUTION.md or ~/.jcode-notes/ma-crm/notes.md

### 3. In-place python/sed edits instead of the edit tools

- Category: Tool economy
- Severity: low
- Evidence: Several multi-file replacements went through heredoc Python, which the harness flagged. They worked, but silent misses are possible (I added asserts only in one script).
- Suggested change: Use `replace`/`apply_patch` for multi-file edits.
- Target: agent behaviour (no file change)

## Worker postmortems

none
