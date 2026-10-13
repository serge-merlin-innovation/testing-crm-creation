# Postmortem: ticket #13 buyer process

- Date: 2026-10-10 11:18
- Role: worker
- Task: Implement GitHub issue #13 (investor profiles, buyer long list, status grid, NDAs, AUTHZ-02 c5, CON-01 c5)
- Model: Claude (jcode)

## Summary

I built the `buyer` module (investor profiles, client exclusions, deal buyers, NDAs), its migration, reminder jobs, the access-matrix rows, the deal Buyers tab, an investor profile panel and an e2e test. Every AC has a test in `tests/integration/crm/test_buyers.py`, 22 in total, all green. Then I merged the feat/ma-crm tip and rebased the migration onto `b3f5916e42d1`, so there is one head. Buyer tables went into merge REFERENCES, with a merge test. After the merge the backend ran 887 passed, frontend unit 234 passed and Playwright 38 passed. Seven admin-session e2e tests fail on the merged tip with or without this ticket's spec.

## Findings

### 1. The merged feat/ma-crm tip has 7 failing admin e2e tests

- Category: Automated checks
- Severity: high
- Evidence: On a fresh DB, the admin specs in page-gate, offboarding-accounts and search-merge-import land on `/login?next=...`. The admin storage session is gone. This happens even with `buyers.e2e.ts` removed. The merger commits used `--no-verify` and do not seem to have run the full Playwright suite.
- Suggested change: make the merger run the full Playwright suite on a fresh DB before committing a merge. Check for a spec that revokes the admin's sessions (logout-everywhere or offboarding) while the shared `admin` storageState is still in use.
- Target: merger instructions / `apps/frontend/tests/e2e/offboarding-accounts.e2e.ts`

### 2. The merge REFERENCES guard is not on the base branch tickets build on

- Category: Navigation
- Severity: medium
- Evidence: The ticket asked me to add my tables to the merge module's REFERENCES. That module (#16) was not on feat/ma-crm when this worktree was created. I had to find it in a sibling worktree and could only wire it after merging the tip.
- Suggested change: say in the notes that REFERENCES and `test_merge_references.py` only exist after #16 merges, and that a parallel ticket adds its rows at merge time.
- Target: `~/.jcode-notes/ma-crm/notes.md`

### 3. Getting an empty DB for alembic autogenerate is a manual hack

- Category: Tool economy
- Severity: low
- Evidence: To autogenerate against a DB without my tables, I moved `src/modules/buyer` out of the tree, ran `upgrade head`, then moved it back. Autogenerate also added unique constraints on `roles.id` and `user.id` that I had to delete by hand.
- Suggested change: add a `scripts/new_migration.sh` that starts a throwaway Postgres, upgrades to head and autogenerates. Exclude or fix the spurious `roles`/`user` unique constraints in `migrations/env.py`.
- Target: `apps/backend/scripts/`, `apps/backend/migrations/env.py`

### 4. No `timeout` binary on macOS

- Category: Tool economy
- Severity: low
- Evidence: `timeout 600 uv run pytest` failed with `command not found`, which cost a round trip.
- Suggested change: in the notes, say to use the tool's own timeout instead of GNU `timeout`.
- Target: `~/.jcode-notes/ma-crm/notes.md`

## Worker postmortems

none
