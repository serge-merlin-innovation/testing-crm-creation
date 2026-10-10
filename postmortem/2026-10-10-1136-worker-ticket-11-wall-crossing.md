# Postmortem: ticket #11 wall crossing, delegation, break-glass, quarterly review

- Date: 2026-10-10 11:36
- Role: worker
- Task: Implement issue #11 (AUTHZ-04, AUTHZ-07, AUTHZ-08, ADM-05, AUTH-02 c5) on feat/ma-crm-t11
- Model: Claude (Jcode)

## Summary

Built a new `access` module (requests, approvers, comments, delegations, quarterly reviews), break-glass as `EmergencyAccess` inside the deal policy, a team-only deal export, and step-up on role change and user export. 16 AC tests written first, then the code; a `/access` page and one e2e. Merged the feat/ma-crm tip (10 conflicting files, all "keep both"), moved the migration onto the new head, and reran 917 backend tests, 237 unit tests and 46 e2e tests, all green.

## Findings

### 1. Adding step-up to existing endpoints silently broke 6 tests in 3 files

- Category: Automated checks
- Severity: medium
- Evidence: Requiring `StepUpUserDep` on `PATCH /users/{id}/role` and `GET /users/export` failed tests in foundation, users and onboarding suites. I only found them through the 7-minute full suite. No list says which endpoints are sensitive.
- Suggested change: Add a unit test that lists the sensitive routes (break-glass, role change, exports) and asserts each depends on `require_step_up`, the way `served_routes` guards deal routes. Then a new export cannot ship without step-up, and the list shows which tests to update.
- Target: apps/backend/tests/unit/interfaces (new test), modules/security/dependencies.py

### 2. Full backend suite takes 7 to 12 minutes and exceeds the foreground timeout

- Category: Tool economy
- Severity: medium
- Evidence: `pytest tests -n 6` took 412s, and 737s after the merge, so it went to the background. Every test builds the schema with `create_all` in its own container DB.
- Suggested change: Note in the notes file to run the full suite in the background with `bg wait`, and consider one schema per xdist worker with transaction rollback.
- Target: ~/.jcode-notes/ma-crm/notes.md, apps/backend/tests/conftest.py

### 3. Merge conflicts in append-only registries are predictable

- Category: Navigation
- Severity: low
- Evidence: Every parallel ticket appends to `api/v1/__init__.py`, `main.py` job registration, `EXCEPTION_MAPPING`, `exceptions.py`, `EventKind`, `messages.ts` and the nav test, so all 10 conflicts were "keep both".
- Suggested change: Have each module expose `register(router)`/`register_jobs()` discovered by walking `src/modules` (as migrations/env.py already does), so a parallel ticket adds files instead of editing shared lists.
- Target: apps/backend/src/interfaces/api/v1/__init__.py, interfaces/main.py

### 4. Playwright `APIResponse.json()` after `context.close()` fails

- Category: Navigation
- Severity: low
- Evidence: The first e2e run failed with "Response has been disposed" because the seed function closed its context before reading the response body.
- Suggested change: Add a line to the E2E gotchas in the notes: read response bodies before closing the request context.
- Target: ~/.jcode-notes/ma-crm/notes.md

## Worker postmortems

none
