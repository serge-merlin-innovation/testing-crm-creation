# Postmortem: merge #13 and #11 into feat/ma-crm, refresh t14

- Date: 2026-10-10 11:51
- Role: worker
- Task: Merge feat/ma-crm-t13 (buyers) and then feat/ma-crm-t11 (wall-crossing) into feat/ma-crm, run every check and the e2e, push, then merge feat/ma-crm into feat/ma-crm-t14.
- Model: Claude (Jcode)

## Summary

The #13 merge had one conflict, in docs/DECISION-REPORT.md: #13's rows 34-37 clashed with the coordinator's row 34. I kept every row and renumbered #13's rows to 35-38. There was already a single Alembic head (3fe8bfeb0d3d on b3f5916e42d1) and OpenAPI had no drift. After that merge: pytest 887 passed, e2e 45/45. The 7 admin e2e failures #13 reported did not come back, which confirms the 4beb001 session-cap fix. Mid-run the coordinator asked me to merge #11 too. That merge was clean (head 7494bc3ff192, decisions 39-43). The final checks passed: pytest 917, ruff/mypy clean, vitest 237, tsc/eslint clean, e2e 46/46. I pushed, then merged feat/ma-crm into t14 cleanly.

## Findings

### 1. The first e2e run died at once because another worktree held port 8100

- Category: Automated checks
- Severity: medium
- Evidence: Playwright exited with "http://localhost:8100/health is already used". Another worktree's suite was running on the shared ports 3100/8100, which are hard-coded in playwright.config.ts. I only found out after about 15 minutes, when I checked the background output.
- Suggested change: Read the ports from env (`E2E_FRONTEND_PORT`/`E2E_BACKEND_PORT`, defaulting to 3100/8100) so parallel worktrees can pick free ports. Failing that, add a small `scripts/wait-e2e-ports.sh` and run it before `playwright test`.
- Target: apps/frontend/playwright.config.ts

### 2. Decision numbers collide on every parallel merge

- Category: Coding standards
- Severity: low
- Evidence: #13 numbered its decisions from 34, and the coordinator had also added a 34, so the rows had to be renumbered by hand. The notes already mention the same thing happening with #15 and #10.
- Suggested change: Have workers label rows by ticket (for example `13-a`) and let the merger give them the final numbers. Or add a unit test that fails when DECISION-REPORT.md has duplicate or non-sequential row numbers.
- Target: docs/DECISION-REPORT.md header, tests/unit

## Worker postmortems

none
