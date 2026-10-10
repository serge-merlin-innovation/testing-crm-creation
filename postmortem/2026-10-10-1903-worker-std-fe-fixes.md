# Postmortem: standards review frontend fixes

- Date: 2026-10-10 19:03
- Role: worker
- Task: Fix S6, S7, N2, N5, N9 and the frontend part of S8 from review-standards.md in apps/frontend.
- Model: Claude (Jcode)

## Summary

I fixed six findings, one commit each. Raw label and fieldset elements now use the Field primitives. Typography classes now use CardTitle, CardDescription, FieldDescription and Alert slots, guarded by a Vitest scan. Two duplicate e2e specs became one, and the scroll observer became a composed ScrollRegion built on the CLI-added scroll-area. Vitest, tsc and eslint stayed clean. The first fresh-DB Playwright run caught an axe regression (one table that my wrap script missed). After the fix, the full suite passed 67/67 on a fresh DB.

## Findings

### 1. No guard that every scrollable Table is keyboard-reachable

- Category: Automated checks
- Severity: medium
- Evidence: My regex wrapped `<Table>` but skipped `<Table aria-label=...>`. Only the full axe e2e on /templates at 375 px caught it, about 3 minutes later.
- Suggested change: Add a Vitest file scan, like typography-guard.test.ts, that fails when a `<Table` outside components/ui is not inside a `ScrollRegion`.
- Target: apps/frontend/tests/unit/lib/

### 2. No formatter in the repo

- Category: Automated checks
- Severity: low
- Evidence: `pnpm prettier` does not exist, and the existing files are not prettier-clean. I had to keep the indentation of the scripted JSX edits consistent by hand.
- Suggested change: Add prettier (or eslint stylistic) to the frontend lint script and format once.
- Target: apps/frontend/package.json

### 3. First-run e2e failure details got lost to `tail`

- Category: Tool economy
- Severity: low
- Evidence: `pnpm playwright test | tail -40` showed only attachment lines, so I had to rerun the full suite to see the error.
- Suggested change: In notes.md, recommend writing the output to a log file and grepping for the `N) ` failure blocks.
- Target: ~/.jcode-notes/ma-crm/notes.md

## Worker postmortems

none
