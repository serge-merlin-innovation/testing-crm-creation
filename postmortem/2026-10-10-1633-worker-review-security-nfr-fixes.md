# Postmortem: review security and NFR fixes

- Date: 2026-10-10 16:33
- Role: worker
- Task: Fix review findings S5, S9-S14, N4, N6, N7 and add the decision-49 form fields on feat/ma-crm-fix-sec
- Model: Claude (Jcode)

## Summary

The session wrote a failing test for each finding, then the fix, one commit per finding: 11 commits plus the decision rows 80-88. It added two Alembic migrations (TOTP encryption, then dropping the weak recovery codes), which keep a single head. It wired the new Key Vault secret through `infra/` without deploying. A new axe e2e found three real WCAG violations, which were fixed. The final run: pytest 1105 passed with `-n 6`, ruff and mypy clean, vitest 256, tsc and eslint clean, and Playwright 64/64 on a fresh throwaway Postgres (port 55612, E2E ports 3161/8161). An earlier full run had 2 flaky failures, and both passed on the rerun.

## Findings

### 1. The review's S5 evidence did not match the code

- Category: Navigation
- Severity: medium
- Evidence: S5 says `infrastructure/app_factory.py:17-26` imports jobs and hooks from modules. That wiring is already in `interfaces/main.py`. The only real violation was an unused `AuditService` import in `infrastructure/auth/routes.py`. Time went into confirming that the cited lines did not exist.
- Suggested change: the reviewer should cite import lines as `grep -n` output, not line ranges. The new `TestDependencyDirection` test now makes this mechanical, so a future review can point at a failing test.
- Target: `apps/backend/tests/unit/modules/test_module_wiring.py` (done), the reviewer prompt

### 2. Exporting the OpenAPI spec depended on an environment flag

- Category: Automated checks
- Severity: medium
- Evidence: after test hooks were gated on `TEST_HOOKS_ENABLED`, `scripts.export_openapi` wrote a spec without the hook schemas, while the contract test (run with hooks on) expected them. The file was reverted by hand, and the script now sets the flag.
- Suggested change: keep the export script and `tests/conftest.py` on one shared env default, as done. The notes should say so for the next person who adds a flag that changes the app.
- Target: `~/.jcode-notes/ma-crm/notes.md`, `apps/backend/scripts/export_openapi.py`

### 3. The full Playwright suite has flaky tests

- Category: Automated checks
- Severity: medium
- Evidence: the first full run failed `offboarding-accounts.e2e.ts:76` (reset button stayed disabled; the HIBP check fails open but may be slow) and `process.e2e.ts:180` (the `v1: 40.00` version line was not rendered yet). Both passed on an isolated rerun and on a second full fresh-DB run.
- Suggested change: inject `StaticBreachList` into the e2e backend (an env switch) so the reset form does not call HIBP. Wait for the offer-version refetch before asserting `v1:`.
- Target: `apps/frontend/playwright.config.ts`, `apps/frontend/tests/e2e/process.e2e.ts`

### 4. No accessibility guardrail existed until this session

- Category: Automated checks
- Severity: medium
- Evidence: axe found focusable-scroll-region, contrast and tab-panel violations that had shipped through 17 tickets.
- Suggested change: keep `accessibility.e2e.ts` in the e2e tier (done). It runs on every route in `app-navigation.ts`, so a new page is covered automatically.
- Target: `apps/frontend/tests/e2e/accessibility.e2e.ts`

### 5. Bulk Python heredoc edits were used instead of the edit tools

- Category: Tool economy
- Severity: low
- Evidence: many multi-file replacements went through `python3 - <<EOF` with asserts. They worked, but the tool repeatedly flagged them, and a one-shot `count == 1` assert on messages.ts matched only the EN block, which needed a second pass for FR and NL.
- Suggested change: use `replace` with `expected_count` for edits that span translations.
- Target: agent habit (no file)

## Worker postmortems

none
