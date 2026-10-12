# Agent experience: what the M&A CRM run teaches the boilerplate, skills and constitution

Read-only analysis, 2026-10-12, of the M&A CRM run of 2026-10-10 (coordinator plus 47 subagent sessions, PR #22).

## Sources

| Source | What it holds | Caveat |
|---|---|---|
| `check-failures.log` | 500 failing checks, 2026-10-10 08:58 to 22:21 | The logger keeps only the last 500 lines (`MAX_LINES` in `scripts/check-failures/log.mjs`), so tickets #1 to #7 (03:00 to 08:58) are lost. It also mixes intended TDD reds with real waste, with no column to tell them apart. |
| `docs/DECISION-REPORT.md` | 86 decision rows (ids 1 to 70 and 80 to 95) | 12 rows were later marked *Superseded*, 4 are *Needs user*. |
| `postmortem/*.md` | 38 postmortems: 36 workers, the coordinator, the ISO 25010 assessment | Several fixes they propose target `~/.jcode-notes/ma-crm/notes.md`, which lives outside the repo and dies with this project. |

Each "still open" status below was checked against the current `feat/ma-crm` tip (`9e9e2fb`).

## The short version

1. **Most agent decisions were spec gaps, not real choices.** Of 86 decisions, about 12 needed a human at run time (vendor, cost, hosting). About 50 answer questions a better spec template would have asked up front: which permission, which recipient, what "monthly" means, the full status list, the fee maths. About 17 are engineering conventions the boilerplate should settle once, as ADRs. About 9 are about the local machine, the process or ticket slicing, and a rule or skill fix would have made them non-decisions.
2. **The worst decisions were silent narrowings.** 12 rows narrowed an acceptance criterion and were reverted after review 2. The constitution has no rule against this, so add one.
3. **About half of the logged failures were not TDD reds.** 267 of 500 lines fall into eight avoidable causes. The biggest are a brittle `Mock(spec=Settings)` pattern (66 lines from 3 runs), late guard tests (73), environment and port collisions (25), domain errors flattened into generic 500s (23) and timing flakes (24).
4. **The same boilerplate defects were found again and again.** Duplicate Alembic ids or several heads came up in 10 postmortems, spurious autogenerate diffs in 9, the throwaway e2e database in 12. The fix for each is still missing on the branch.
5. **Run knowledge leaked out of the repo.** The e2e recipe, the merger runbook and the gotchas went into private notes. The next project starts from zero.

---

## 1. `check-failures.log`

### 1.1 Shape

| Check | Failures |
|---|---|
| backend `test:integration` | 219 |
| backend `test:unit` | 113 |
| frontend `test:e2e` | 101 |
| frontend `test:unit` | 67 |
| lint, format, typecheck | 0 (in this 500-line window) |

247 (branch, test) pairs failed exactly once, which looks like a healthy red then green. 103 tests failed more than once, which points to thrash.

### 1.2 Failures by cause

The log has no "this was a planned red" flag, so I bucketed by error text. The 233 "assertion" lines hold most of the real TDD reds, along with some regressions. Every other bucket is waste that a boilerplate or skill change can remove.

| # | Cause | Lines | Example | Root cause | Fix (target) |
|---|---|---|---|---|---|
| A | `Mock(spec=Settings)` drift | **66** | `Mock object has no attribute 'TEST_HOOKS_ENABLED'` (26x), `BREACH_CHECK_ENABLED` (26x), `TOTP_ENCRYPTION_KEY` (12x) | `test_production_validator.py` builds Settings as `Mock(spec=Settings)`. Every new setting the validator reads breaks every test in the file at once (13 of its 20 tests failed together each time). | Build a real `Settings(_env_file=None, **overrides)` through one `make_settings()` fixture. **Boilerplate.** |
| B1 | Frontend source-scan guards (typography, `toLocale*`, raw dates) | 34 | `expected '"use client"…' not to match /toLocale(Date\|Time)?String\(/` | The rules exist only as tests, so agents learn them by failing. | Put the rule list into an agent-facing `docs/agents/frontend.md` and add ESLint rules (`no-restricted-syntax`), so the editor flags them before the test does. **Boilerplate + docs.** |
| B2 | Exact navigation list | 18 | `expected [ '/overview', … (6) ] to deeply equal [ … (4) ]` | `app-navigation.test.ts` asserts the full route list per role, so every new page breaks it. | Assert per permission ("admin sees /users", "analyst never sees /users"), not the whole list. **Boilerplate test style; add to `tdd` anti-patterns.** |
| B3 | i18n coverage | 13 | `Add FR and NL to translations.json for:` | The guard sits in the unit tier, but agents iterate on integration files and never run it. | A fast `pnpm check:quick` step (see 4.3) after any user-facing string. **Skill.** |
| B4 | OpenAPI and `.env.example` sync | 8 | `docs/api/openapi.json is out of date` | Generated artifact committed by hand. | Regenerate in `lint:fix` and pre-commit. **Boilerplate.** |
| C | Timing and perf flakes | 24 | `test_nfr02_on_200k_contacts` (11x), `Test timeout of …ms exceeded` (13x) | A wall-clock budget runs inside the shared suite while 4 to 8 suites run at once (load average about 46). | Mark it `@pytest.mark.perf` and leave it out of the default run. CI's k6 job already gates performance. **Boilerplate.** |
| D | Environment, ports, e2e state | 25 | `localhost:8100/health is already used`, `Missing CSRF token`, `has no saved TOTP secret`, `Config file '/app/.env' not found` | Shared ports and DB across worktrees, a local `.env` leaking into unit tests, a stale `.auth`. | One `pnpm test:e2e:fresh` script (throwaway Postgres on a free port, migrate, seed, wipe `.auth`, run), and Settings tests that ignore `.env`. **Boilerplate.** |
| E | asyncpg multi-statement SQL | 17 | `cannot insert multiple commands into a prepared statement` | One fixture sent several statements in one `execute`, and every test in the file erred at setup. | One line in `docs/agents/backend.md`. **Docs.** |
| F | Domain error flattened to a generic 500 | 23 | `{"detail":"Something went wrong. Please try again."}` | `EXCEPTION_MAPPING` keeps the message only for `ValidationError` and `InsufficientCreditsError`. This is deliberate (`test_domain_error_returns_generic_message`), but agents do not know it. Raised in 4 postmortems too. | **Human decision, then an ADR**: either keep generic messages and document "user-facing 4xx text is raised as `HTTPException` in the route", or add a `user_facing` marker on `DomainError` subclasses whose detail is safe to show. **Boilerplate + ADR.** |
| G | Contract drift across branches | 28 | `formatAmount is not a function`, `format_date() takes 1 positional argument`, `KeyError: 'added'` | Parallel branches change a shared helper's signature. | Merge the integration tip before reporting (the `implement` skill already says so, but under load workers skipped it), plus shared test builders (`inbound_payload(**overrides)`). **Skill + boilerplate.** |
| H | Domain rules tripping fixtures | 11 | `enterprise_number is required for a Belgian company`, `code name must not contain the client`, similar-name duplicate | Fixtures hand-build records and collide with validations. | Fixture builders that always produce valid, unique records (`uniqueCompanyName()`, `freshClient()`). **Boilerplate test kit.** |

### 1.3 Improve the log itself

- **Tell TDD reds apart.** Add a `phase` column. The wrapper can infer it: a failure in a test file that is new or modified in the working tree is `red`, and anything else is `regression`. Otherwise every analysis like this one has to guess.
- **Keep history.** Rotate per day (`check-failures/2026-10-10.log`) instead of truncating at 500 lines. This run lost its first six hours.
- **Record the worktree and a run id**, not only the branch. 20 branches ran in about 10 worktrees.
- **Add a repeat counter view.** One test failing 6 times on one branch is the cheapest signal that an agent is stuck. `retro-auto` could read it.

---

## 2. `DECISION-REPORT.md`

### 2.1 What the 86 decisions were about

| Kind | Rows | Count | Who should have decided, and where |
|---|---|---|---|
| **Vendor, cost, hosting, publishing** | 5, 7, 11, 12, 19, 27, 60, 61, 62, 63, 65, 95 | 12 | Human, **at spec time**. A "Vendors and hosting" section in `to-spec`. The *default* (port, fake, "unavailable" adapter) belongs in the constitution so it stops being a decision. |
| **Which permission or role may do X** | 20, 25, 30, 31, 37, 39, 42, 47, 50, 58, 94 | 11 | Human, in the spec. `to-spec` must produce a role x action matrix for every new capability. |
| **Time, quantity and threshold semantics** ("12 months", "monthly", "this week", "business hours", similarity 0.5) | 15, 21, 26, 43, 45, 53, 59, 66, 93 | 9 | Human, in the spec. `to-spec` must flag every vague quantity and ask for a number. |
| **Domain model and status semantics** (what a conflict is, the full buyer status list, KYC per mandate or per company) | 14, 16, 17, 24, 35, 36, 38, 40, 49 | 9 | Human, in the spec and `CONTEXT.md`. Enumerations must be listed in full. |
| **Calculation and aggregation rules** (fee maths, funnel, forecast, win/loss) | 32, 44, 46, 54, 56, 57 | 6 | Human, in the spec, as **worked examples** (inputs and expected output). They double as the test oracle that `tdd` requires. |
| **Recipient, routing, ownership** (who gets the task, who owns a contact) | 18, 22, 23, 41, 48, 52 | 6 | Human, in the spec. Every reminder or notification criterion names its recipient. |
| **Confidentiality edge cases** (what may leak through counts, feeds, search) | 28, 29, 33, 51, 55, 70, 86 | 7 | Human, **once**, as a principle in `CONTEXT.md` or an ADR ("reveal less, never name or single out a hidden deal"). After that, every case is a mechanical application. |
| **Engineering conventions** (test hooks, i18n catalogue, audit on every mutation, CSV injection, secret encryption, email port, module wiring) | 13, 64, 67, 68, 69, 80, 81, 82, 83, 84, 85, 87, 88, 89, 90, 91, 92 | 17 | Human, **once per boilerplate**, as ADRs in `docs/adr/` that every fork inherits. |
| **Local machine and git state** (`--no-verify`, deleted Docker volume, foreign Postgres, stash and `.env` left in place) | 1, 2, 9, 10, 34 | 5 | Nobody: the constitution should forbid it, so it is never a decision. |
| **Skill or boilerplate mismatch** (no `ROADMAP.md`, no spec issue) | 3, 4 | 2 | Fix the `implement` skill (see 4.2). |
| **Ticket slicing** (UI missing from #5, admin UI deferred) | 6, 8 | 2 | Fix `to-tickets`: a ticket is a full vertical slice, UI included. |

So **about 12 of 86 (14%)** decisions were legitimately the agent's to escalate at run time. The other 74 had a better home: the spec (about 48), an ADR (17), or a rule or skill fix (9, the last three rows).

### 2.2 The narrowings

These rows each narrowed a stated criterion and were reverted by review 2: **8, 16, 17, 23, 35, 36, 37, 42, 53, 55, 57, 86** (12 rows). Review 1 caught none of them. The pattern was always the same: the agent judged the spec behaviour "too strict" or "would break work" and logged a decision instead of asking. The decision report looked like disclosure, so nobody pushed back.

**Rule needed:** a decision may only *interpret* a criterion, never *narrow* it. A narrowing stops the ticket and goes to the user (see 4.1).

### 2.3 The format fights parallel work

- Row ids collided across branches (rows 16 to 20, 34, 39 to 43, 89). 5 postmortems mention renumbering. Ids also jump from 70 to 80, and row 6 sits after row 10.
- "Superseded by review 2" is appended inside the original cell, so reading the table means parsing prose.
- Nothing ties a row to its criterion in a checkable way.

**Proposed format:** one file per spec, `docs/decisions/<spec>.md`, with ticket-scoped ids (`T10-3`, `R2-1`) and fixed columns:

| Id | Criterion | Kind | Decision | Why | Reverse by | Status |
|---|---|---|---|---|---|---|

`Kind` takes one of four values: `interpretation`, `default-applied` (a documented default from an ADR or the constitution), `needs-user`, `deviation`. `Status` is `open`, `confirmed` or `superseded by <id>`. A small unit test checks that ids are unique, that every row names a criterion id that exists in the spec, and that no row of kind `deviation` is `open` on a branch marked ready.

---

## 3. Postmortems: recurring findings

Counted across the 38 files. "Open" means verified as still unfixed on the branch tip.

| Finding | Postmortems | Status | Fix |
|---|---|---|---|
| E2E needs a throwaway, migrated, seeded DB with no script. Ports shared. Compose maps `5432:5432` while `.env` uses 55432. | 12 (0340, 0419, 0432, 0915, 0921, 1151, 1358, 1421, 1517, 2205, main, ISO) | Ports env **done**. Fresh-DB script and compose port **open**. | `scripts/e2e-fresh.sh` plus `pnpm test:e2e:fresh`. Map `${POSTGRES_PORT:-5432}:5432`. Make `playwright.config.ts` refuse to run against 5432 or the `.env` port. Make the pre-push hook use the same script, so nobody needs `--no-verify` (decisions 1 and 10). |
| Alembic autogenerate emits spurious `unique` on `roles.id` and `user.id`, and the template output fails ruff | 9 (0357, 0456, 0459, 0905, 0915, 0936, 1002, 1028, 1421) | **Open** (`unique=True` still on both PKs; `script.py.mako` still uses `typing.Union`) | Drop `unique=True` on PKs, modernise the mako template, add ruff as an Alembic `post_write_hook`, add `alembic check` to CI. |
| Parallel branches pick the same Alembic id, or leave two heads | 10 (0357, 0445, 0449, 0459, 0828, 0921, 1106, 1118, 1358, main) | **Open** (no `get_heads` test exists) | Unit test: unique revision ids, exactly one head, no hand-typed ids (reject runs like `abcdef`). |
| Guard tests (module wiring, i18n, `.env.example`, step-up) surface only in the full run | 7 (0445, 0456, 0936, 1506, 1925, 2001, 2205) | Open | `pnpm check:quick` (all unit guards, about 25 s) named in the `implement` worker steps and run by pre-commit. Plus a "new module checklist" in `docs/agents/backend.md`. |
| Suites exceed the 10-minute tool cap (integration 15 to 55 min under load) | 7 (1136, 1434, 1653, 1925, 2030, 2203, ISO) | Open (`test:integration` still serial; an auto-applied `slow` marker exists in `tests/integration/conftest.py` but nothing documents `-m "not slow"`) | `-n auto` by default, document the `slow` deselect for iteration, a documented "run it detached with a log file" recipe, and a coordinator cap on concurrent full runs. |
| E2E specs collide on data (non-unique names, non-`exact` locators, no wait after a mutating click) | 8 (0905, 0936, 1506, 1743, 1949, 2001, 2030, 2205) | Partly (`runId()` exists) | ESLint: ban `Date.now()` in `tests/e2e/**` and require `exact: true` on short role names. Builders in `identities.ts`. An `e2e.md` conventions doc. |
| Bulk edits through Python or `sed` heredocs silently dropped code | 6 (0340, 0419, 0445, 1633, 1652, 1653) | Habit | Constitution line, plus a harness hook that warns on `python3 - <<` or `sed -i` against `src/`. |
| Domain error messages swallowed into a generic 500 | 4 (0432, 0905, 0915, 1002) + 23 log lines | **Open** | See log cause F. |
| Decision-number collisions | 5 (1106, 1151, 1347, 2203, main) | Open | See 2.3. |
| `uv sync` drops dev tools, so a fresh worktree cannot run pytest | 4 (0456, 0459, 1358, 1506) | **Open** (still `optional-dependencies`) | Move dev tools to `[dependency-groups] dev`. |
| Perf test flakes under load | 4 (1633, 2001, 2203, 2205) | Open | See log cause C. |
| Every ticket edits the same registries (router list, job list, deal tabs) | 2 (1028, 1136) | Open | Each slice registers itself, discovered by walking `src/modules`. Parallel tickets then add files instead of editing shared lines. |
| Coordinator idled for hours on wake-ups that never arrived | main | Open | Coordinator polls every 15 min and never relies on a wake alone (`implement` skill or swarm prompt). |
| Code review run inside a worker cannot spawn its two reviewers. The review 2 spec reviewer (ladybug) died after 28 min without writing anything. | main | Open | `code-review`: the root spawns one reviewer per axis and splits the spec axis by epic above about 100 criteria. Reviewers write incrementally. Note: the coordinator blamed the job's size, but the server log shows ladybug died on an account rate limit (`429 rate_limit_error`, 3 retries over 2 min) at a 211K-token context, well below the window. Splitting helped only by luck; the real fixes are incremental writes, a longer backoff on 429, and a guard that respawns a `failed` member at once. |
| Merge state lost when a worker died | 1347 | Open | Mergers commit WIP or write progress to the notes before long steps. |
| Dependency audit not a gate (3 critical Next.js CVEs) | ISO | **Open** | CI: `pnpm audit --prod --audit-level=high` and `uvx pip-audit`. |
| `AGENTS.md` points to `CONTEXT.md` and `docs/adr/`, which do not exist | ISO | **Open** | Create both. They are the natural home for most decisions in 2.1. |
| gitleaks and prettier silently absent | 0432, 0936, 1743, 1903 | Open | The setup skill installs gitleaks. Pick one formatter for the frontend. |

### 3.1 Knowledge that must move into the repo

Many postmortems target `~/.jcode-notes/ma-crm/notes.md` (291 lines). Those notes made the run work, and they vanish for the next fork. Promote what is generic:

- `docs/agents/backend.md`: new module checklist, error mapping rule, offline-safe migrations (no `op.get_bind()` reads), a new permission needs a migration grant, `set_session_clock`, two login throttles, asyncpg one-statement rule, enumerate routes with `served_routes`, never `app.routes`.
- `docs/agents/e2e.md`: fresh-DB script, ports, `runId()` and the builders, row-scoped locators with `exact: true`, read response bodies before closing the context, wait for the response after a mutating click.
- `docs/agents/running-checks.md`: which tier to run when, how long each takes, run long suites detached, no GNU `timeout` on macOS.
- `docs/agents/merging.md`: the merger runbook (`git merge -m`, keep both sides of registry conflicts, single-head check, full e2e on a fresh DB before the merge commit).

---

## 4. Recommendations by target

### 4.1 `docs/agents/CONSTITUTION.md` (cross-project rules only)

The constitution is near-identical in every fork, so add only rules that are not CRM-specific. Proposed lines, in its style:

- **An agent never narrows an acceptance criterion.** Where a criterion is ambiguous, it takes the reading that does more of what the criterion says, and logs it. Where a criterion cannot be met as written, it stops and asks. *(Prevents rows 8, 16, 17, 23, 35, 36, 37, 42, 53, 55, 57, 86.)*
- **Hooks are never skipped.** `--no-verify` is a human act, like merging. *(Rows 1, 10.)*
- **State the agent did not create is never stopped, deleted or reset**: databases, Docker volumes, processes, ports, stashes, untracked files. When it is in the way, the agent works around it on its own ports and says so. *(Rows 2, 10, 34.)*
- **Every external service sits behind a port with an in-memory fake.** Until the user picks a vendor, the production adapter reports the service as unavailable. This is the default, not a decision. *(Rows 5, 7, 27 become `default-applied`.)*
- **Source files are edited with the edit tools, never by scripts that rewrite them.** *(6 postmortems.)*
- **Decisions an agent takes go in `docs/decisions/<spec>.md`, one row per decision, naming the criterion it touches.** (Format in 2.3.)

### 4.2 Skills

**`to-spec`** (the biggest lever, because it removes decisions before they exist). Add an **ambiguity sweep** to step 2. Before the confirmation message, the agent checks every story against this list and turns each hit into a flagged gap with a proposed answer:

1. Every capability names the roles or permissions that may use it (output: a role x action table).
2. Every duration, period, threshold and count is a number with a unit ("12 months" becomes 365 days or calendar months? "monthly" becomes which day?).
3. Every enumeration (statuses, stages, kinds) is listed in full.
4. Every reminder, task or notification names its recipient and its trigger.
5. Every calculation has at least one worked example with inputs and expected output.
6. Every "owner" or "responsible" is defined per record type.
7. Every external service names a vendor, or is explicitly "port plus fake, vendor later".
8. Every criterion that touches confidential data says what may appear in counts, search, feeds and exports.

Also add two template sections, **Vendors and hosting** (cost, region, publishing) and **Definitions**, written to `CONTEXT.md` when the user approves.

**`to-tickets`**: a ticket is a full vertical slice (API *and* screen) unless the user says otherwise (rows 6, 8). Each ticket lists the criteria ids it owns, so decisions and review traces can cite them. A shared-contract ticket (registries, helpers, i18n plumbing) runs first, so parallel tickets do not each invent their own.

**`implement`**:
- New step 1b, **pre-flight questions**: before any code, each frontier ticket's agent reads its ticket and returns *only* open questions, classified with the eight sweep categories. The coordinator batches them into one message to the user (or one `/to-questionnaire`). Implementation starts after the answers land in the spec. This moves most `interpretation` rows to the human, up front, at the cost of one round trip per frontier.
- Worker rule: a worker may log only `interpretation` and `default-applied` rows. Anything else ends the ticket with status `blocked: needs user`, and the worker does not ship a narrowed version.
- Give each worker a decision-id prefix (`T10-`) and a migration-head check before it reports.
- Name `pnpm check:quick` after every slice and `pnpm test:e2e:fresh` before reporting (the #4 branch broke the whole e2e setup and never ran it).
- The coordinator polls worker status every 15 minutes. It caps concurrent full-suite runs. At the end it removes testcontainers and the worktrees.
- Fix steps 10 to 12: skip `ROADMAP.md` when it is absent, and create the spec issue if the spec has none (rows 3, 4).

**`tdd`**: add two anti-patterns seen in the log. *Mock of a config object* (`Mock(spec=Settings)`, 66 failures): use a real object built by a factory. *Whole-list assertions* where the behaviour is per item (navigation, 18 failures). Add "planned reds are tagged" if the logger gets a `phase` column.

**`code-review`**: the coordinator spawns the reviewers itself. The spec axis is split by epic above about 100 criteria and reads the decision log against the spec to catch narrowings. Reviewers cite `grep -n` output, not line ranges (1633).

**`retro-auto`**: read the day's `check-failures` log for the session's branch. Report tests that failed 3 or more times, and any lines in causes A to H. Point at the existing open finding rather than filing a duplicate.

### 4.3 Boilerplate (code and config)

Ordered by failures avoided per hour of work:

1. `make_settings()` test factory, and remove `Mock(spec=Settings)` (66 log lines).
2. Decide the domain-error message policy (generic by design today) and write it as an ADR, plus a `user_facing` marker if detail should show (23 log lines, 4 postmortems).
3. `scripts/e2e-fresh.sh` plus `pnpm test:e2e:fresh`. Make `playwright.config.ts` fail fast on port 5432 or the `.env` port. Map the compose port through `${POSTGRES_PORT}`. Point the pre-push hook at the script (25 log lines, 12 postmortems, decisions 1, 2, 10).
4. Alembic hygiene: a single-head and unique-id test, no `unique=True` on PKs, a modern mako template, a ruff `post_write_hook`, `alembic check` in CI (19 postmortems).
5. `pnpm check:quick`: every unit guard on both sides, under 30 s, run by pre-commit and named in skills (guard causes B1 to B4: 73 lines).
6. ESLint rules for what the vitest scans check today (typography, `toLocale*`, raw dates, `Date.now()` in e2e, `exact: true`), so the editor catches them first.
7. Pytest: `-n auto` by default, `perf` and `slow` markers excluded from the default run, the perf budget only in CI's k6 job (24 log lines, 7 postmortems).
8. Self-registering slices (routers, jobs, tabs), so parallel tickets stop conflicting on shared lists.
9. Test builders: backend `create_mandate()` with a fresh client by default, `inbound_payload(**overrides)`; frontend `uniqueCompanyName()`, `freshClient()` (11 log lines, contract drift).
10. `[dependency-groups] dev` in `pyproject.toml`.
11. CI dependency audit (`pnpm audit`, `pip-audit`).
12. The check-failures logger: a `phase` column, daily rotation, a worktree column (see 1.3).

### 4.4 Docs scaffolding in the boilerplate

- Create `CONTEXT.md` and `docs/adr/` (`AGENTS.md` already points to them). Seed the boilerplate ADRs that this run had to invent: email and other external ports, test hooks behind a default-off flag, the in-process job runner and its limits, in-memory rate limiting, i18n as one catalogue keyed on English, an audit row for every mutating route, CSV-injection-safe exports, encrypted secrets at rest, module wiring rules. That covers the 17 "engineering convention" decisions, so the next project starts with them as `default-applied`.
- Add `docs/agents/backend.md`, `e2e.md`, `running-checks.md`, `merging.md` (3.1).
- Add `docs/decisions/` with the format and test from 2.3.

---

## 5. Suggested order of work

| Step | Change | Removes |
|---|---|---|
| 1 | Constitution: no narrowing, no `--no-verify`, no touching foreign state, ports-with-fakes default | 12 reverted rows, 5 machine rows, 3 vendor rows |
| 2 | `to-spec` ambiguity sweep, Definitions and Vendors sections, `CONTEXT.md` | about 48 spec-gap rows |
| 3 | `implement` pre-flight questions, decision kinds, scoped ids | the rest of the run-time interpretations, id collisions |
| 4 | Boilerplate items 1 to 5 in 4.3 | about 200 of the 267 avoidable log lines, about 30 postmortem findings |
| 5 | ADRs for the 17 conventions, `docs/agents/*.md` | the repeat cost in the next fork |
| 6 | Logger `phase` column and rotation | makes the next version of this report exact instead of estimated |

## Appendix: method

- The log was bucketed with `awk` on the error column. The buckets in 1.2 are approximate: the "assertion" bucket (233) mixes TDD reds and real regressions, and the logger cannot tell them apart.
- The decision kinds in 2.1 are my classification of each row's text. A row could fit two kinds, and I gave it the one that names who should have decided.
- Postmortem counts come from each finding's title and suggested change, cross-checked by grepping all 38 files for the finding's key terms (re-verified 2026-10-12). "Open" was checked by grepping the current tree (`unique=True` in the user and role models, `typing.Union` in `script.py.mako`, no `get_heads` in tests, `optional-dependencies` in `pyproject.toml`, `5432:5432` in compose, no `audit` in `ci.yml`, no `CONTEXT.md` or `docs/adr/`).
