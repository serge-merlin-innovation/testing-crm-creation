# Postmortem: two-factor login, lockout, login alerts (#2)

- Date: 2026-10-10 04:19
- Role: worker
- Task: Implement issue #2 (AUTH-01/02/06/12) on feat/ma-crm-t2
- Model: Claude (Jcode)

## Summary

Built a `security` module (TOTP enrolment with QR and recovery codes, trusted devices with an admin switch, 5-in-15 lockout with admin email, audited unlock and 2FA reset, new country/device alerts with a travel suppression, last-login profile, step-up dependency), email and geo-IP ports with in-memory fakes, a two-step login form and profile card. 220 backend tests, 168 vitest, 15 Playwright E2E pass. Merged the #5 tip early and chained the migration onto c3d4e5f6a7b8.

## Findings

### 1. crudauth's in-memory per-IP/per-account lockout fights the app's own account lock

- Category: Navigation
- Severity: medium
- Evidence: The admin-unlock test kept getting 429 after unlock because crudauth's LockoutPolicy keyed by IP and account still held counters; I had to read crudauth's policy.py and delete its raw keys (`login:lock:user:...`). The existing rate-limit test also had to switch to an unknown account since the app now answers 423 first.
- Suggested change: Document in docs/agents (or the notes file) that the login has two throttles (crudauth IP+account lockout, app `login_failures` lock) and how `clear_throttle` reconciles them; consider moving the lockout policy behind a small wrapper instead of reaching into crudauth key names.
- Target: apps/backend/src/modules/security/service.py, docs/agents/

### 2. Tests assuming exactly one audit row per login broke silently on the new flow

- Category: Coding standards
- Severity: low
- Evidence: Three foundation tests used `select(AuditEntry)).scalar_one()` or asserted the full action list; enrolment adds `user.2fa_enrolled` and they failed.
- Suggested change: Reviewer rule: audit assertions filter by `action`, never assume the whole table.
- Target: docs/agents/CONSTITUTION.md (review guidance) or a test helper `audit_actions(db, action)` in foundation/helpers.py

### 3. Bash heredoc + python edits instead of the edit tools

- Category: Tool economy
- Severity: low
- Evidence: Several in-place python replacements silently missed after ruff reformatted a function (clear_account_throttle stayed, causing an undefined-name error).
- Suggested change: Use the Edit/replace tools, which fail loudly on missed matches; run ruff format only after the edit batch.
- Target: agent behaviour (no file)

### 4. E2E needs a fresh DB and a wiped .auth after 2FA

- Category: Information access
- Severity: low
- Evidence: A rerun against a DB where accounts were already enrolled needs the saved TOTP secrets; a container restart in a new shell lost DATABASE_URL and the web server failed with exit 3 and no hint.
- Suggested change: A `scripts/e2e-fresh.sh` that starts the throwaway Postgres, migrates, seeds, wipes tests/e2e/.auth and runs Playwright.
- Target: scripts/

## Worker postmortems

none
