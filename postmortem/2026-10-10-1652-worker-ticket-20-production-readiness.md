# Postmortem: ticket #20 production readiness (NFR-01..04, cross-cutting)

- Date: 2026-10-10 16:52
- Role: worker
- Task: Implement GitHub issue #20 (security, performance, availability, languages/accessibility, cross-cutting criteria) on feat/ma-crm-t20
- Model: Claude (Jcode)

## Summary

Hosting guarantees (EU regions, TLS 1.2+, AES-256, 35-day geo backups, maintenance window, uptime monitor) now live in `infra/` with a contract test. An `operations` module covers recovery drills (RPO/RTO), pentest findings (30-day rule plus release gate) and 48-hour maintenance notices. There is a k6 load test and a pytest perf budget on 200k contacts, plus a ZAP baseline. Errors, notifications and emails come out in EN/FR/NL with a coverage guard, and a saved user language is synced by the proxy. Belgian formats are used everywhere. An axe + 375 px Playwright sweep runs over every page. An audit-coverage route guard and a deal-wall leak sweep cover the cross-cutting criteria. Final results: pytest 1147 passed, vitest 460, Playwright 66/66 on a fresh DB, ruff/mypy/tsc/eslint clean. The branch has the feat/ma-crm tip 27f0e11 merged and a single Alembic head, 53c790ab1c3e.

## Findings

### 1. Two audit dependencies looked alike but differed on CSRF

- Category: Navigation
- Severity: high
- Evidence: I added `AuditContextDep` to the inbound mail webhook. The integration test passed, but the e2e failed with 403 "Missing CSRF token". `get_audit_context` depends on `get_optional_user`, which runs crudauth's session dependency and its CSRF check. Integration clients carry no CSRF cookie, so the check never ran there. I added `SystemAuditContextDep` for webhooks.
- Suggested change: Add a docstring on `get_audit_context` warning that it enforces CSRF when a session cookie is present, and point webhooks to `SystemAuditContextDep`. Also add a line to the notes about it.
- Target: apps/backend/src/modules/audit/dependencies.py, ~/.jcode-notes/ma-crm/notes.md

### 2. Display-format changes break e2e assertions that only Playwright sees

- Category: Automated checks
- Severity: medium
- Evidence: The switch to Belgian formats broke 7 e2e specs that asserted raw values such as "500000.00", "2031-01-06" and `navigation "Primary"`. Vitest and tsc stayed green, so the break only showed in the 3-minute Playwright run.
- Suggested change: Add a vitest check that greps `tests/e2e/*.ts` for `toContainText("\d+\.\d{2}")` and ISO-date literals in visible-text assertions. Also export the navbar landmark names as constants that the e2e helpers import.
- Target: apps/frontend/tests/unit/lib/i18n.test.ts, apps/frontend/tests/e2e/identities.ts

### 3. Multi-worker uvicorn startup races on DDL

- Category: Information access
- Severity: medium
- Evidence: `fastapi run --workers 2` on a fresh DB crashed one worker with "tuple concurrently updated" (startup seeding and DDL racing). k6 then hung for 6+ minutes on a half-dead server before I noticed.
- Suggested change: Document "one worker" in the notes. Make startup seeding take a `pg_advisory_lock`, so multi-worker or multi-replica starts are safe.
- Target: apps/backend/src/interfaces/main.py (lifespan), notes

### 4. Ad-hoc python file rewrites through Bash

- Category: Tool economy
- Severity: low
- Evidence: Many edits went through `python3 - <<EOF` replace scripts instead of Edit/apply_patch. One regex line-splitter looped forever and burned a 2-minute timeout. The harness also warned repeatedly.
- Suggested change: Use the Edit tool's `edits` array for multi-site changes. For mechanical wrapping, rely on `ruff format`.
- Target: agent behaviour (no file)

### 5. No guard yet that a new page enters the a11y sweep

- Category: Automated checks
- Severity: low
- Evidence: `accessibility-languages.e2e.ts` covers pages from `PAGE_AUDIENCE` plus hand-listed detail pages. Detail routes like `/companies/[id]` are not swept unless added by hand.
- Suggested change: Derive dynamic routes from `src/app/**/[id]/page.tsx` and fail when one has no seeded id in the spec.
- Target: apps/frontend/tests/e2e/accessibility-languages.e2e.ts

## Worker postmortems

none
