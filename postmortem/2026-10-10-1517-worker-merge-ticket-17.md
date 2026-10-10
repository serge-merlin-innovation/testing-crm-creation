# Postmortem: merge #17 into feat/ma-crm

- Date: 2026-10-10 15:17
- Role: worker
- Task: Merge feat/ma-crm-t17 (reporting) into feat/ma-crm, run every gate, push, clean up, notify #20
- Model: Claude (Jcode)

## Summary

Merged feat/ma-crm-t17 (11cc156) with --no-ff, clean, as a55a4ae. Alembic single head 87dc941ce57c on 846f5d7b5c39. Gates: pytest 1072 passed (-n 6, 9.5 min), ruff, ruff format and mypy clean, vitest 253, tsc and eslint clean, Playwright 58/58 on a freshly recreated `crm` DB in crm-t17-pg :55517 (E2E ports 3197/8197, .auth wiped, seeded with scripts.setup_initial_data). Pushed, removed crm-t17-pg, DMed #20. Smooth session: no failures.

## Findings

### 1. Nothing stops Playwright from hitting the developer's real database

- Category: Automated checks
- Severity: medium
- Evidence: The e2e backend webServer inherits POSTGRES_* from the shell, and the gitignored .env sets POSTGRES_PORT=55432. Pointing it at the throwaway DB relies on remembering to export POSTGRES_PORT. The only "never localhost:5432" guard is the coordinator's prompt. I verified afterwards by querying the container by hand.
- Suggested change: Make playwright.config.ts require an explicit E2E_POSTGRES_PORT (pin it into the backend webServer env) and refuse to start when it is unset, 5432, or the .env port.
- Target: apps/frontend/playwright.config.ts

### 2. pytest still needs a POSTGRES_PORT=5432 workaround

- Category: Automated checks
- Severity: low
- Evidence: Notes say test_settings::test_database_url_fallback_to_constructed fails under the user's .env. Every merger has to remember to prefix `POSTGRES_PORT=5432`.
- Suggested change: Have the test build Settings with `_env_file=None` and monkeypatch the env, so it ignores the local .env.
- Target: apps/backend/tests (test_settings.py)

### 3. Merger runbook lives only in private notes

- Category: Navigation
- Severity: low
- Evidence: The full sequence (drop/create DB, migrate, seed, wipe tests/e2e/.auth, `pnpm build` before Playwright, port overrides) is spread across merger sections of ~/.jcode-notes/ma-crm/notes.md. That notes file is outside the repo.
- Suggested change: Add a short `scripts/e2e-fresh.sh <pg-port> <fe-port> <be-port>` that runs the whole sequence, and point to it from docs/agents.
- Target: scripts/, docs/agents/

## Worker postmortems

n/a (worker role)
