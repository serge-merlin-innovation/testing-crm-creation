# Postmortem: ticket #10 fees, fee visibility and invoices

- Date: 2026-10-10 10:28
- Role: worker
- Task: Implement issue #10 (DEAL-05, AUTHZ-06, REP-07, ROLE-01 c4/c5) on feat/ma-crm-t10
- Model: Claude (Jcode)

## Summary

Built a `fee` module (fee terms, expected/final fee with percent, fixed, minimum and Lehman tiers, creditable retainers, post-engagement amendment rule, invoices, back-office invoice task at closing), a `fees.read` permission, a compliance summary grant, a Fees page and a deal Fees tab. 14 new integration tests, 7 new matrix rows, fee unit tests and a 3-test Playwright file. Merged feat/ma-crm (ticket #9), resolved 7 conflicts, rebased the migration to a single head. 701 backend, 219 unit and 31/31 e2e pass.

## Findings

### 1. Offline migration test caught a data migration only at full-suite time

- Category: Automated checks
- Severity: medium
- Evidence: The first migration used `connection.execute(select(...))`, which returns None under `alembic upgrade --sql`. Only `test_offline_migration_accepts_percent_encoded_database_url` caught it, 4 minutes into the full run.
- Suggested change: Add a note to the migration template, or a ruff/AST check under `tests/unit` that flags `op.get_bind()` in migrations, pointing to plain `op.execute(sql)`.
- Target: apps/backend/tests/unit/infrastructure/database/, migrations/script.py.mako

### 2. Every parallel ticket edits the same four hotspots

- Category: Navigation
- Severity: medium
- Evidence: The merge with #9 conflicted in `interfaces/api/v1/__init__.py`, `interfaces/main.py`, `mandate/policy.py` (grant aliases at the end of the file), `page-audience.ts`, `deal-view.tsx` tabs, the access matrix list and `openapi.json`. All were append-at-end edits.
- Suggested change: Let slices register routers, startup hooks and deal tabs from their own module (a registry list per slice), so parallel tickets stop touching shared lines. At minimum, note in notes.md that these files always conflict and are resolved by keeping both sides.
- Target: ~/.jcode-notes/ma-crm/notes.md, apps/backend/src/interfaces/api/v1/__init__.py

### 3. Test-id lint rule surfaced only after the UI was written

- Category: Coding standards
- Severity: low
- Evidence: `data-testid` in fees-tab.tsx failed eslint `no-restricted-syntax`. The rule is good, but the notes do not mention it, so a test was written around it first.
- Suggested change: Add one line to notes.md Frontend section: no `data-testid`; use accessible names or `data-*` attributes describing the data.
- Target: ~/.jcode-notes/ma-crm/notes.md

### 4. `timeout` missing on macOS

- Category: Tool economy
- Severity: low
- Evidence: `timeout 600 uv run pytest` failed with "command not found", costing a round trip.
- Suggested change: Use the Bash tool timeout parameter instead; note it in notes.md "Running checks".
- Target: ~/.jcode-notes/ma-crm/notes.md

## Worker postmortems

none
