# ISO/IEC 25010:2023 assessment of the M&A CRM

Branch `feat/ma-crm`, 2026-10-10. Measured against the 2023 product quality model: 9 characteristics, each scored 1 to 5. The bar is "ready for production with confidential M&A data".

Method: quality gates run locally, then four read-only reviews (security, reliability and performance, maintainability and flexibility, interaction capability and compatibility and safety). I checked the most serious findings again myself. Nothing was deployed or changed.

## Verdict

**Not production-ready yet. The code is solid, but it ships with known critical vulnerabilities, and its hosting can't meet its own targets.** The application logic, access control and test discipline are above average. The blockers are a dependency upgrade, the hosting configuration and running more than one replica.

| Characteristic | Score | One line |
|---|---|---|
| Functional suitability | 4 | All 20 tickets built, but email, geo-IP, company register and inbound mail are only stubs |
| Performance efficiency | 2 | Fast on a laptop, but CI misses the budget 9x and production gets 0.25 vCPU |
| Compatibility | 3.5 | Versioned API, OpenAPI, ICS, CSV/XLSX. Paging and error format are inconsistent |
| Interaction capability | 3 | Full en/fr/nl parity and axe tests. Every page has the same title, no loading states, one-click deletes |
| Reliability | 2.5 | Good backups and recovery drill. In-memory sessions, single replica, unlocked job runner |
| Security | 3 | Strong design (2FA, deal wall, audit). **3 critical CVEs in Next.js**, no CSP/HSTS |
| Maintainability | 3 | Clean slices and ports, but 2 import cycles, large services and 27 of 31 modules without unit tests |
| Flexibility | 3.5 | Env config, ports/adapters, non-root multi-stage Docker. Can't scale out |
| Safety | 3.5 | Merge undo, step-up 2FA on exports, maintenance guard. Destructive UI actions without confirmation |

## Quality gates (run locally)

| Gate | Result |
|---|---|
| Lint (ruff, eslint) | Pass |
| Typecheck (mypy, tsc) | Pass, but mypy is not strict |
| Backend unit tests | 359 passed |
| Frontend build | Pass |
| Backend integration tests | 1,012 passed in 15 min (4 xdist workers, testcontainers Postgres) |
| `pnpm audit --prod` | **21 vulnerabilities: 3 critical, 11 high**, 6 moderate, 1 low |
| `pip-audit` | pyjwt 2.13.0 and urllib3 2.7.0 flagged |

## Must fix before go-live

| # | Characteristic | Finding | Evidence | Fix |
|---|---|---|---|---|
| 1 | Security | Next.js 16.2.12 has unauthenticated remote code execution advisories (3 critical), plus sharp, postcss and nanoid highs | `apps/frontend/package.json`, `pnpm audit --prod` | Upgrade `next` to >=16.3.6 (latest 16.3.x), refresh the lockfile, upgrade pyjwt and urllib3, and run the audit in CI as a failing gate |
| 2 | Reliability, Performance | Backend and frontend run on 0.25 vCPU with `minReplicas = 0` (scale to zero) | `infra/parameters/backend-container-app.bicepparam:133-135`, `frontend-container-app.bicepparam:51-53` | At least 1 vCPU / 2 GiB and `minReplicas = 1`, then repeat the load test on staging |
| 3 | Reliability | Login sessions live in process memory, so every restart, scale event or deploy logs everyone out | `apps/backend/src/infrastructure/auth/setup.py:10` (`backend="memory"`) | Store sessions in Redis (Azure Cache) or Postgres |
| 4 | Capacity | CI load test misses its budget: search p95 9,016 ms (budget 1,000), 22 req/s for 50 users | Decision 95, `docs/research/load-test.md` | Fix 2 and 3, then add uvicorn workers and replicas |
| 5 | Reliability | `maxReplicas = 1` is forced because sessions, the API rate limiter and the job runner are all in-process. The job runner has no lock, so 2 replicas would run every job twice | `infra/backend-container-app.bicep:73`, `api_access/rate_limit.py:34`, `infrastructure/jobs/runner.py:81` | Shared rate limiter, Postgres advisory lock (or a separate worker) for jobs, then allow 2+ replicas |
| 6 | Reliability | The database is `Standard_B1ms` Burstable with HA disabled | `infra/parameters/postgres-server.bicepparam:19-25` | General Purpose tier with zone-redundant HA, matching the 99.5% target |
| 7 | Security | No CSP, `X-Frame-Options`/`frame-ancestors` or HSTS on frontend pages. The relay drops the backend's HSTS | `apps/frontend/next.config.ts` | Add `headers()` with a strict CSP, frame-ancestors 'none', HSTS and nosniff |
| 8 | Functional | Email only goes to the log. Invitations, password resets, 2FA alerts and maintenance notices never reach anyone | Decision 7 | Choose a provider (for example Azure Communication Services) and implement the email port |

## Should fix soon

| # | Characteristic | Finding | Fix |
|---|---|---|---|
| 9 | Security (non-repudiation) | The app connects as the Postgres server admin, which owns `audit_log` and can disable its append-only trigger | Separate app role without ownership or `ALTER` on `audit_log` |
| 10 | Security (authenticity) | A TOTP code can be reused within its ~90 s window, both at login and for step-up | Store the last used time step per user and refuse reuse |
| 11 | Reliability | Excel imports (up to 500k rows) run in one transaction in the web process. A failing import retries every minute forever and blocks the queue | Batch commits, a retry cap with a "failed" status, eventually a worker |
| 12 | Reliability | No liveness/readiness probes on the container apps. No `pool_pre_ping` or statement timeout | Probes on `/health/ready`, `pool_pre_ping=True`, `statement_timeout` |
| 13 | Performance | The deal list and 49 other list endpoints have no paging | Uniform `page`/`items_per_page` on every list |
| 14 | Interaction | Every page is titled "M&A CRM" (WCAG 2.4.2). A list that is still loading looks empty | Per-page `metadata` titles, skeleton or loading states |
| 15 | Safety | Removing a team member, link, picklist value, stage criterion or delegation, discarding an inbox email, merging and committing an import all run in one click. Some deletes ignore a failed response | shadcn `AlertDialog` confirmations, handle error responses |
| 16 | Interaction | Erase-contact and offboard dialogs label Cancel as "Try again". Per-field validation messages stay English in fr/nl | Fix the labels, translate the field errors |
| 17 | Compatibility | The documented error format differs from what the API returns. `openapi.json` lists 5 `/test-hooks` paths that prod doesn't serve. Paging uses two styles | Align the schema, exclude test hooks from the export, one paging style |
| 18 | Security | Public network access on Postgres and Key Vault, no upload size cap | Private endpoints or firewall rules, request body limit |

## Could fix

| # | Characteristic | Finding |
|---|---|---|
| 19 | Maintainability | Import cycles user/role/session/security and company/contact, and `infrastructure/auth` imports the `user` module. Tests allow all three instead of failing on them |
| 20 | Maintainability | `create_application` has cyclomatic complexity 64, `mandate.authorize` 18. Five services are 650 to 820 lines |
| 21 | Testability | mypy not strict, 27 of 31 modules have no unit tests (the integration suite carries them), no coverage threshold |
| 22 | Analysability | `AGENTS.md` points to `CONTEXT.md` and `docs/adr/`, which don't exist. The README is still the boilerplate one |
| 23 | Functional | KBO/BCE, NBB, geo-IP and inbound mail are ports with "unavailable" adapters (decisions 5, 7 and 27) |

## Strengths worth keeping

- **Access control:** mandatory 2FA, a deal wall that returns 404 for unstaffed deals (no bypass found in the spot-checked routes), field-level fee visibility, and step-up 2FA on mass exports.
- **Accountability:** an append-only audit log, plus a call-graph test that every mutating route writes to it.
- **Secrets handling:** hashed API tokens, a constant-time webhook secret check, and test hooks that refuse to run in production.
- **Data:** all 142 foreign keys are indexed, trigram indexes back search, and backups are daily plus point-in-time recovery for 35 days, geo-redundant in the EU, with a documented restore drill.
- **Languages and accessibility:** en, fr and nl have the same 863 keys, `<html lang>` follows the user, and there are axe tests and a 375 px layout test.
- **Constitution:** the frontend follows the shadcn-only UI rules. The Dockerfiles are pinned, multi-stage and run as non-root.

## Limits of this assessment

- Functional suitability is judged from the ticket map (all 20 tickets built) and the stubbed adapters in the decision report. It is not a criterion-by-criterion trace of `docs/specs/ma-crm.md`.
- Security spot-checked about 15 services, not every route. It's no substitute for the yearly penetration test that NFR-01 c4 requires.
- No browser test was run as a logged-in user (2FA). The E2E suite was not run here.
- Performance numbers come from the existing load-test reports. No new run was done against staging, because staging doesn't exist yet.
- Scores are expert judgement against the ISO characteristics, not a certified ISO/IEC 25040 evaluation.
