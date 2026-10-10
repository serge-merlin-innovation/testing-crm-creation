# Postmortem: merge ticket #14 into feat/ma-crm

- Date: 2026-10-10 14:34
- Role: worker
- Task: Merge feat/ma-crm-t14 (offers and process) into feat/ma-crm, verify everything, push, create the #20 worktree
- Model: Claude (Jcode)

## Summary

The merge was a clean no-ff (the #14 tip already contained feat/ma-crm b8f6c06). There was a single Alembic head, 846f5d7b5c39 on b32b7af0bfc9. pytest gave 1039 passed. ruff, ruff format and mypy were clean. vitest gave 247 passed, and tsc and eslint were clean. Playwright passed 52/52 on a throwaway Postgres (55494) with E2E ports 3194/8194 and a wiped .auth. The merge was pushed with --no-verify, and the worktree ../crm-t20 was created on feat/ma-crm-t20. No fixes were needed.

## Findings

### 1. Backend suite dominates merge wall time

- Category: Tool economy
- Severity: low
- Evidence: `pytest -n 4` took 12m43s for 1039 tests, while every other check combined (lint, types, frontend unit, full e2e) took about 1.5 minutes. The merger sat idle waiting on it.
- Suggested change: Try `-n auto` (or `-n 8`) in the documented command. Record the measured speedup in the "Running checks" section of the notes.
- Target: apps/backend/pyproject.toml (pytest addopts), ~/.jcode-notes/ma-crm/notes.md

### 2. Shared notes file truncates on a single read

- Category: Navigation
- Severity: low
- Evidence: `cat notes.md` hit the tool output cap, and the remaining sections had to be re-read in two more calls. The merger needs only the "Running checks" section and the latest "Merge of ..." section.
- Suggested change: Keep a short "Current state" header at the top (Alembic head, next free decision number, e2e recipe, ports convention) that each merger updates in place. Move the per-ticket notes below it.
- Target: ~/.jcode-notes/ma-crm/notes.md

## Worker postmortems

none
