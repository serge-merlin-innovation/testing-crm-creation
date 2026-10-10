# Postmortem: review 2 backend standards fixes

- Date: 2026-10-10 19:25
- Role: worker
- Task: Fix backend findings S1-S5, S8, S9 and nits N1, N3, N4, N6, N7, N8, N10 from review-standards.md
- Model: Claude (jcode)

## Summary

One commit per finding: a single email port, shared authorization helpers, one deal-wall sweep and one audit-coverage file, review/ticket IDs replaced with spec criteria, the audit scope and notification visibility inverted into ports registered in interfaces/main.py with a slice-cycle guard, and seven nits including the access-request rate limit. Backend pytest (-n 6) found one failure, missing FR/NL for the new 429 message, which was fixed and rerun. ruff and mypy are clean, and Playwright passed 68/68 on a throwaway Postgres (port 55491).

## Findings

### 1. The i18n coverage guard only surfaced in the 20-minute full run

- Category: Automated checks
- Severity: medium
- Evidence: The new 429 detail in access/routes.py failed `test_i18n_coverage.py` only at the end of the full suite. Targeted runs of the slice tests passed.
- Suggested change: Run `tests/unit` (25 s, includes every AST/coverage guard) as a fast pre-commit or a documented "after any user-facing string" step.
- Target: notes.md (backend section) or `.husky`/pre-commit config

### 2. The full deal-access matrix takes 9+ minutes

- Category: Tool economy
- Severity: medium
- Evidence: `test_deal_access_matrix.py` alone ran 480 cases in 561 s with -n 6, which overflowed the foreground timeout. Every case rebuilds the world and seeds a matrix deal.
- Suggested change: Use a module-scoped seeded world with per-test transactions, or mark the matrix `slow` and document `-m "not slow"` for iteration.
- Target: apps/backend/tests/integration/crm/test_deal_access_matrix.py

### 3. Slice cycles had no guard until now

- Category: Coding standards
- Severity: low
- Evidence: Three audit cycles came in with the B1 fix unnoticed. `TestSliceIndependence` now fails on new cycles, with an allow-list for `company/contact` and `role/security/session/user`.
- Suggested change: Split those groups and shrink `KNOWN_SLICE_CYCLES` to empty.
- Target: apps/backend/tests/unit/modules/test_module_wiring.py

## Worker postmortems

none
