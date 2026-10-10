# Postmortem: spec C F1 UI screens

- Date: 2026-10-10 19:49
- Role: worker
- Task: Build timeline panels, /tasks, notification preferences card and /audit over existing APIs (review finding F1)
- Model: Claude (Jcode)

## Summary

Added `components/record-timeline.tsx` (log/edit/delete/restore activities, notes) mounted on the deal Activities tab and as panels on /companies and /contacts, a /tasks page, a notification preferences card on /profile and an /audit page gated on audit.read, with EN/FR/NL strings, nav and PAGE_AUDIENCE entries, and four e2e specs. Vitest 476, tsc, eslint and the full Playwright suite (73) pass on a throwaway Postgres. One full-suite run failed first because new button aria-labels changed existing table-cell accessible names.

## Findings

### 1. Row action aria-labels silently break other specs' cell locators

- Category: Coding standards
- Severity: medium
- Evidence: Adding `aria-label="Timeline <name>"` to a button in a table cell made `getByRole("cell", { name })` in crm-records.e2e.ts match two cells (strict-mode violation). Only the full e2e run showed it, 4 minutes in.
- Suggested change: Note in the e2e conventions doc that row actions are located by scoping to the row (`getByRole("row", ...).getByRole("button", ...)`), and that cell locators use `exact: true`.
- Target: docs/agents (e2e conventions) or tests/e2e/identities.ts header comment

### 2. Typography guard lives only in a sibling worktree

- Category: Automated checks
- Severity: low
- Evidence: The guard from ../crm-std-fe had to be copied in temporarily to check new files; on this base it flags many pre-existing files, so it could not be committed here.
- Suggested change: Land the guard on feat/ma-crm with the existing violations fixed, so every branch runs it in vitest.
- Target: apps/frontend/tests/unit/lib/typography-guard.test.ts

## Worker postmortems

none
