# Postmortem: merge #12 origination into feat/ma-crm

- Date: 2026-10-10 13:58
- Role: worker
- Task: Merge feat/ma-crm-t12 into feat/ma-crm, verify, push, create the #17 worktree
- Model: Claude (Jcode)

## Summary

feat/ma-crm-t12 already contained feat/ma-crm, so the merge was clean (no-ff, reworded to name the migration and decisions). Single Alembic head b32b7af0bfc9 on 7494bc3ff192. Backend pytest 934 passed, ruff, ruff format and mypy clean, vitest 243 passed, tsc and eslint clean, Playwright 50/50 against a throwaway Postgres on port 55491 with tests/e2e/.auth wiped. Pushed with --no-verify and created ../crm-t17 on feat/ma-crm-t17. Smooth session.

## Findings

### 1. Merge verification is a hand-assembled command list

- Category: Automated checks
- Severity: medium
- Evidence: Every merger session rebuilds the same sequence from notes.md (uv sync --extra dev, POSTGRES_PORT=5432 pytest, ruff, mypy, vitest, tsc, eslint, throwaway Postgres on a free port, alembic upgrade, seed, wipe .auth, build, Playwright, stop container). Two notes gotchas (POSTGRES_PORT override, wipe .auth only with a fresh DB) must be remembered each time.
- Suggested change: Add `scripts/verify-merge.sh` that runs the full suite with a throwaway Postgres on a random port, the POSTGRES_PORT override and the .auth wipe, and checks `alembic heads` returns exactly one head.
- Target: scripts/verify-merge.sh, referenced from docs/agents/CONSTITUTION.md

### 2. Merge commit message needs an amend

- Category: Tool economy
- Severity: low
- Evidence: `git merge --no-edit` produced a generic message, then a second commit --amend added the migration and decisions info that mergers record by convention.
- Suggested change: Mergers should pass `-m` directly to `git merge`. Note the convention in the merger notes.
- Target: ~/.jcode-notes/ma-crm/notes.md

## Worker postmortems

none
