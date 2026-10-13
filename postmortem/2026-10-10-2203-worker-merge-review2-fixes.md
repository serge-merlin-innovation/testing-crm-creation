# Postmortem: merge review-2 fix branches

- Date: 2026-10-10 22:03
- Role: worker
- Task: Merge std-fe, std-be, spec-a, spec-b, spec-c-ui into feat/ma-crm, verify, push.
- Model: Claude (jcode)

## Summary

I merged the five branches in order. I resolved conflicts in compliance/buyer services, the wall-crossing, KYC and matrix tests, the fee forecast, company and contact list views, the profile page and DECISION-REPORT (spec-a's 89 became 94). I re-parented spec-b's migration onto spec-a's head and wrapped seven unwrapped tables in ScrollRegion. The record timeline moved from list-page toggles onto companies/[id] and contacts/[id]. pytest passed at every merge, except one load-induced perf flake that passed on rerun. ruff, mypy, vitest 507, tsc and eslint were clean. Playwright passed 80/80 twice on a fresh DB.

## Findings

### 1. Backend pytest takes about 55 minutes under shared machine load

- Category: Tool economy
- Severity: high
- Evidence: Each `pytest -n 6` run took 54-55 minutes at load average ~35 (10 CPUs, 57 containers, 9 pytest processes from other workers). Three runs per merge batch dominated the session. I only kept the timing reasonable by merging in a side worktree and running pytest at two merge commits in parallel.
- Suggested change: Have coordinators cap concurrent full-suite runs (one merger plus N workers), or add a `pytest -m "not slow"` tier for intermediate merges, with the full suite once at the end.
- Target: ~/.jcode/swarm-prompt.md, apps/backend/pyproject.toml (markers)

### 2. NFR-02 perf test is a wall-clock assertion inside the unit/integration suite

- Category: Automated checks
- Severity: medium
- Evidence: `test_nfr02_on_200k_contacts` failed with `/api/v1/mandates/ p95 6.179s >= 2.0s` under load. It passed alone in 25s.
- Suggested change: Mark it `@pytest.mark.perf` and exclude it from the default run (CI's load-test job already gates performance), or skip it when `os.getloadavg()[0] > cpu_count`.
- Target: apps/backend/tests/integration/performance/test_nfr02_performance.py

### 3. ScrollRegion rule has no guard, only typography does

- Category: Automated checks
- Severity: medium
- Evidence: The std-fe typography guard caught nothing new, but 7 `<Table>`s in spec-b/spec-c-ui were unwrapped, and I found them only by grepping by hand.
- Suggested change: Add a vitest file scan next to typography-guard.test.ts: every `<Table` outside components/ui must sit inside a `<ScrollRegion` in the same file (count check is enough).
- Target: apps/frontend/tests/unit/lib/scroll-region-guard.test.ts

### 4. Decision numbers clash on every parallel batch

- Category: Coding standards
- Severity: low
- Evidence: Both std-be and spec-a took 89. Notes record the same renumbering after earlier merges.
- Suggested change: Have the coordinator hand each fixer a reserved decision range in its prompt.
- Target: ~/.jcode-notes/ma-crm/notes.md / coordinator prompt

### 5. pnpm refuses symlinked node_modules in side worktrees

- Category: Navigation
- Severity: low
- Evidence: `pnpm vitest` in the merge worktree failed in runDepsStatusCheck. Calling `node_modules/.bin/*` directly worked. I also committed the `.venv` symlink once by accident, because `apps/backend/.venv` as a symlink is not matched by the `.venv/` gitignore pattern.
- Suggested change: Add `.venv` (no trailing slash) to .gitignore, and note the direct-binary trick in notes.md (done).
- Target: .gitignore

## Worker postmortems

none
