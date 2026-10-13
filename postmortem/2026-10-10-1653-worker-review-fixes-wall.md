# Postmortem: review fixes, Chinese wall and audit

- Date: 2026-10-10 16:53
- Role: worker
- Task: Fix review findings B1-B3, S1-S4, S6-S8, S15, N1-N3 on feat/ma-crm-fix-wall
- Model: Claude (Jcode)

## Summary

Fixed 14 review findings test-first, one commit each, plus a follow-up S7 commit for a regression that only Playwright caught. Every finding has a failing test first. The full backend suite passed (1212, -n 6, about 18 min), along with ruff, mypy, vitest (253), tsc and eslint. Playwright passed 58/58 on a throwaway Postgres (port 55571, E2E ports 3171/8171). No migration was needed, the single head is still 87dc941ce57c, and the OpenAPI spec did not change. Decision 70 records S2.

## Findings

### 1. Webhook routes inherit CSRF through AuditContextDep

- Category: Automated checks
- Severity: high
- Evidence: For S7 I added `AuditContextDep` to `POST /email-logging/inbound`. That dependency resolves `get_optional_user`, which reads the session cookie and enforces CSRF. The integration test used a cookie-less client and passed. Playwright sends the webhook from a signed-in browser context and got 403 "Missing CSRF token". Only the e2e run caught it.
- Suggested change: Add a unit test that walks `served_routes` and asserts that secret-authenticated routes (inbound webhook, calendar ics, oauth token) carry no dependency on `get_optional_user`/`get_current_user`. Also add a note in notes.md under #15.
- Target: apps/backend/tests/unit/modules/test_module_wiring.py, ~/.jcode-notes/ma-crm/notes.md

### 2. The test helpers module loads twice under relative and absolute imports

- Category: Navigation
- Severity: medium
- Evidence: `test_foundation.py` imports `.helpers` relatively, while `deal_helpers` imports `tests.integration.foundation.helpers`. That gives two `TOTP_SECRETS` dicts, so `step_up` raised KeyError for a user that deal_helpers had logged in.
- Suggested change: Make foundation tests use absolute imports (`from tests.integration.foundation.helpers import ...`), or add a ruff `TID252` (relative imports) ban for tests.
- Target: apps/backend/pyproject.toml (ruff), tests/integration/foundation/test_foundation.py

### 3. The access-matrix runtime exceeds tool foreground limits

- Category: Tool economy
- Severity: medium
- Evidence: With two new personas and the collection table, `test_deal_access_matrix.py` plus `test_public_api.py` passed 600 s at -n 6, and one background run was killed by its own timeout. Each parametrised case rebuilds the whole world with 9 logins.
- Suggested change: Seed the matrix world once per module (a module-scoped fixture with a DB snapshot, or a per-worker template database), or split the matrix into its own CI job.
- Target: apps/backend/tests/integration/crm/test_deal_access_matrix.py

### 4. Commit hygiene with `git commit -a` while other work is unstaged

- Category: Coding standards
- Severity: low
- Evidence: `git commit -qam "N1..."` swallowed the uncommitted S8 matrix file. It had to be split with a soft reset.
- Suggested change: When the brief asks for one commit per finding, stage explicit paths and never use `-a`. Add this as a line in the swarm brief template, not in AGENTS.md.
- Target: coordinator brief template

### 5. Python heredoc edits instead of the edit tool

- Category: Tool economy
- Severity: low
- Evidence: Many multi-file edits went through `python3 - <<EOF` string replacements, which the harness flags. They did assert on misses, but the diffs were not reviewable in the transcript.
- Suggested change: Use `apply_patch` for multi-file edits. No repo change needed.
- Target: none (agent habit)

## Worker postmortems

none
