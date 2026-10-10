# Postmortem: ticket #6 mandates, deal team, deal-access policy (+ #5 pages)

- Date: 2026-10-10 04:32
- Role: worker
- Task: Implement GitHub issue #6 and the missing ticket #5 frontend pages on feat/ma-crm
- Model: Claude (Jcode)

## Summary

I built the `mandate` and `notification` backend modules: code-name mandates, deal team with expiry, the wall-crossing register, labelled https links, field history and optimistic concurrency. The single deal-access policy sits in `mandate/policy.py`, and a deal-access matrix suite fails when a deal endpoint has no row in it. I also added list/search endpoints for companies and contacts. On the frontend I added the deals, deal, companies, contacts and picklists pages, a Not found page, Vitest unit tests for the deal logic and Playwright E2E tests for the browser-only ACs. Results: backend 325 tests, frontend unit 174, E2E 22 (run twice), and ruff, mypy, tsc and eslint all clean. Three commits on feat/ma-crm, nothing pushed.

## Findings

### 1. FastAPI 0.140 hides included routes from `app.routes`

- Category: Navigation
- Severity: medium
- Evidence: My first route walk in the access-matrix guard iterated `app.routes` for `APIRoute` and found none, because included routers show up as `_IncludedRouter`. The guard passed vacuously until the "stale rows" assertion caught it. The wiring test avoids the problem by going through `app.openapi()`, but nothing documents why.
- Suggested change: Add a one-line pointer in the backend notes or a docs file: "enumerate routes via `mandate.policy.served_routes(app.routes)` or `app.openapi()`, never `app.routes` directly". Also assert non-empty in any route-walking test (done here).
- Target: docs/agents (backend conventions) or `~/.jcode-notes/ma-crm/notes.md` (done)

### 2. DomainError messages are silently replaced by a generic message

- Category: Navigation
- Severity: medium
- Evidence: I mapped `LastLeadPartnerError` and similar errors to user-facing 409 texts in `EXCEPTION_MAPPING`, but the error handler renders `GENERIC_ERROR_MESSAGE` for every non-ValidationError domain error. I only found this by reading `test_error_handler.py`, and then had to translate them with `HTTPException` in the routes.
- Suggested change: Add a comment or doc pointer at `EXCEPTION_MAPPING` saying that only ValidationError and InsufficientCreditsError keep their detail text, and that user-facing conflicts belong in an `HTTPException` in the route.
- Target: apps/backend/src/modules/common/constants.py (docstring) or backend docs

### 3. E2E needs a manually prepared database with no wrapper

- Category: Automated checks
- Severity: low
- Evidence: One Playwright run failed because the backend web server started without `DATABASE_URL`, so it seeded an unmigrated DB. The notes describe a manual docker + alembic + seed + build sequence.
- Suggested change: Add a `scripts/e2e-local.sh` (or a `test:e2e:local` package script) that starts a throwaway Postgres, migrates, seeds, builds and runs Playwright with the env set.
- Target: apps/frontend/package.json, scripts/

### 4. No component-render test tier in the frontend

- Category: Automated checks
- Severity: low
- Evidence: Vitest runs in the node environment without Testing Library, so deal UI behaviour (conflict banner, new-tab links) can only be tested as pure lib functions or through the slow E2E tier.
- Suggested change: Decide explicitly (ADR) whether to keep the two-tier design. If component tests are wanted, add happy-dom and @testing-library/react.
- Target: docs/adr/

### 5. Gitleaks missing from the pre-commit guardrail

- Category: Automated checks
- Severity: low
- Evidence: Every commit printed "gitleaks not installed, secret scan skipped". The secret scan silently does nothing on this machine.
- Suggested change: Fail loudly, or install gitleaks via a setup script / devcontainer, so the hook actually scans.
- Target: .husky/pre-commit, setup skill

## Worker postmortems

none
