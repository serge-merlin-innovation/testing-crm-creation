# Postmortem: merge #20, fix-sec and fix-wall into feat/ma-crm

- Date: 2026-10-10 17:43
- Role: worker
- Task: Merge feat/ma-crm-t20, feat/ma-crm-fix-sec and (on a mid-task change of plan) feat/ma-crm-fix-wall into feat/ma-crm, stabilise the e2e flakes, verify, push.
- Model: Claude (Jcode)

## Summary

Merged the three branches with no-ff merges. Chained fix-sec's migrations after #20's (87dc941ce57c -> 53c790ab1c3e -> 646a8075b1e6 -> 2c2b74c8ce6a, single head). Where both branches built the same NFR checks, kept #20's stronger copy and dropped fix-sec's operational-checks workflow, `ops/`, `nfr-checks.md`, `seed_load_data.py` and `accessibility.e2e.ts` (decision 88 rewritten). Resolved the S7 audit overlap: fix-wall's injected `AuditService` and required context, #20's old/new values on `activity.updated`, and the `_sender` checks for both SPF/DKIM and `has_record_access`. Also added FR/NL for five new messages and fixed four tests that broke only when the branches met. Flakes: added a `BREACH_CHECK_ENABLED` switch (false in Playwright, refused on staging and production) and made the offers e2e wait for each save. Replaced every e2e timestamp `RUN` with a random `runId()`, because reruns on one DB collided in fuzzy search and the duplicate check. Final checks: pytest 1323 passed (-n 6), ruff, mypy, vitest 464, tsc and eslint all clean. Playwright passed 68/68 three times in a row, on a fresh DB and then twice more on the same DB.

## Findings

### 1. E2E names built from `Date.now().toString(36)` collide across runs on one database

- Category: Automated checks
- Severity: high
- Evidence: Run 2 on the reused DB failed search-merge-import ("No results." never shown: the previous run's `Lefèvremv2j0qws` matched `Lefèvremv2jd9ry` fuzzily). Runs 3 and 4 failed crm-records ("Possible duplicates: Lingua Partners mv2ju5b4"). Timestamps in base 36 share a 4-5 character prefix within a day. A 10-character random token was still not enough for the fuzzy spec. It needed 24, because "Hélène Lefèvre" is shared by every run.
- Suggested change: Done here: `runId()` in `tests/e2e/identities.ts`. Add an eslint `no-restricted-syntax` rule that bans `Date.now()` in `tests/e2e/**`, so new specs use `runId()`.
- Target: apps/frontend/eslint.config.mjs

### 2. Parallel branches change shared contracts without a cross-branch test run

- Category: Automated checks
- Severity: medium
- Evidence: Each branch was green alone, but merging broke 4 tests and the i18n coverage test. fix-sec made SPF/DKIM mandatory, but #20 and fix-wall had inbound payloads without it. fix-wall made Read-only 403 on the calendar feed, but #20's wall sweep expected 200. fix-wall renamed `saved_filter.updated` to `.shared`. Five new error strings had no FR/NL. All of this surfaced only at merge time, after a 12-minute pytest.
- Suggested change: When a coordinator runs parallel fix branches, have each worker merge the others' current tips (or feat/ma-crm after every merge) before reporting. Or add a test helper `inbound_payload(**overrides)` that already carries the verdicts, so a new required field changes one place.
- Target: apps/backend/tests/integration/crm/helpers (new helper), coordinator swarm prompt

### 3. Duplicate NFR work across #20 and fix-sec

- Category: Navigation
- Severity: medium
- Evidence: Both branches built axe/375 px e2e, k6, ZAP, Bicep assertions and an ops doc. On merge, half of fix-sec's S14 commit was deleted (7 files).
- Suggested change: The review file should say which findings an in-flight ticket already covers (S14 = #20 NFR-01..04), so the fixer skips them.
- Target: ~/.jcode-notes/ma-crm/review.md (coordinator), docs/agents/ notes on review triage

### 4. Prettier drift in an e2e spec goes unnoticed

- Category: Automated checks
- Severity: low
- Evidence: `npx prettier --check tests/e2e/search-merge-import.e2e.ts` already failed before this session's edit. Commits use --no-verify, so the husky/lint-staged step never runs.
- Suggested change: Add `prettier --check` for apps/frontend to the CI `frontend` job, so --no-verify commits are still caught.
- Target: .github/workflows/ci.yml

## Worker postmortems

none
