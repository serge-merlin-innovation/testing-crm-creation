# Postmortem: resume ticket #12 merge of #11

- Date: 2026-10-10 13:47
- Role: worker
- Task: Finish the interrupted merge of feat/ma-crm (#11) into ticket #12, verify ORI ACs, run all checks.
- Model: Claude (Jcode)

## Summary

The previous worker died mid-merge. On resume the conflicts were in fact already resolved on disk (no markers, decisions 50-53, migration already re-pointed to 7494bc3ff192) but not staged. I regenerated docs/api/openapi.json with scripts.export_openapi, confirmed a single Alembic head, committed the merge (fca90fc). Every ORI-01..04 AC already had an integration test. Backend 934 passed, ruff/format/mypy clean, vitest 243 passed, tsc and eslint clean, Playwright 50/50 on a throwaway Postgres (55481).

## Findings

### 1. Merge state was not recorded when a worker died

- Category: Information access
- Severity: medium
- Evidence: git said "UU" for both files, but the content was already resolved. I had to grep for markers and row numbers to know what was left.
- Suggested change: workers record merge progress (files resolved, steps left) in ~/.jcode-notes/ma-crm/notes.md or a WIP commit message before long steps.
- Target: docs/agents/CONSTITUTION.md (merge procedure)

### 2. Decision-row ownership is coordinated by hand

- Category: Automated checks
- Severity: low
- Evidence: renumbering rows per ticket (39-43, 44-49, 50+) is passed in the prompt. A duplicate or gap would go unnoticed.
- Suggested change: a unit test asserting decision numbers in docs/DECISION-REPORT.md are unique.
- Target: apps/backend/tests/unit (or scripts/check-failures)

## Worker postmortems

none
