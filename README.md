# merlin-delivery-boilerplate

Merlin Innovation's internal product boilerplate, forked per client project.

**Stack:** Next.js (web) · FastAPI (api) · PostgreSQL · Azure (Container Apps, AI Foundry) · Turborepo.

## Start a new project

1. **Create the repository from this template and clone it.** The name becomes every Azure resource
   name, so treat it as final once Infra has run: lowercase letters, digits and hyphens, at most 20
   characters.

   ```bash
   gh repo create merlin-ai-labs/<name> --template merlin-ai-labs/merlin-delivery-boilerplate --private
   gh repo clone merlin-ai-labs/<name>
   ```

   GitHub fills the new repository a few seconds after creating it; a clone that comes up empty was
   too early, so delete it and clone again.

2. **Open Claude Code in the clone and run `/setup`.** It locks `main` with the template's branch
   rules (a template copies files, not rules), builds the local stack, replaces the template's
   placeholder names, creates the issue labels the agent skills use, connects GitHub to Azure
   without stored passwords (OIDC), maps the project's design system from `docs/design-system/` onto the shadcn theme
   (a Claude Design export: the fonts, and the tokens in `globals.css`), and opens a pull request with its changes.

Two steps belong to people, and `/setup` hands them over:

- **An Azure admin** gives the deployment identity two roles, once: Contributor and Role Based
  Access Control Administrator. The pipelines can't grant these to themselves. `/setup` opens an
  issue assigned to the admin with the command to run, `scripts/grant-azure-roles.sh`.
- **You** add three secrets with `scripts/set-github-secrets.sh`: the Postgres admin password, a
  GitHub token for the image registry, and the backend secret key. Never paste them into the chat.

Run `/setup` again to finish what was pending. It never deploys; Infra and CD stay manual.

## Layout

```
apps/
  web/            Next.js front end (fork of ixartz/SaaS-Boilerplate) — owns auth/tenant/billing
  api/            FastAPI service (fork of Benav Labs) — owns domain/document/AI data
packages/
  shared/         Generated typed API client + shared auth-claims contract
  design-tokens/  The single per-client rebrand surface (light/dark tokens, brand assets)
infra/            Bicep templates + per-template .bicepparam files (deployed by GitHub Actions)
.github/          CI, CD and manual Infra workflows + composite deploy actions
docs/             Runbook, rebrand guide, design-review checklist, ADRs
```

## Quick start

Requires `node >=22`, `pnpm`, `uv`, and Postgres — natively, or in a container via Docker.

```bash
pnpm install
```

Copy the env files, then review `POSTGRES_PASSWORD`, `SECRET_KEY` and `FIRST_SUPERUSER_PASSWORD`
in `apps/backend/.env`:

```bash
cp apps/backend/.env.example apps/backend/.env
cp apps/frontend/.env.example apps/frontend/.env
```

Start Postgres — `pnpm db:up` runs it in a container from
`apps/backend/docker-compose.yml`, or install it natively and create the database named by
`POSTGRES_DB`. Then install Python deps, apply migrations and seed the first role and superuser:

```bash
cd apps/backend && uv sync --all-packages --all-extras && cd ../..
pnpm --filter @merlin/backend db:migrate
cd apps/backend && uv run python -m scripts.setup_initial_data && cd ../..
```

The E2E suite also needs a browser, which `pnpm install` does not fetch:

```bash
pnpm --filter @merlin/frontend exec playwright install --with-deps chromium
```

Run both apps with `pnpm dev`.

Then open http://localhost:3000 and sign in.

## Check failure log

Every failed lint, format, typecheck or test run on this machine appends one line per error to
`check-failures.log` at the root of the main checkout (shared by every git worktree, gitignored,
last 500 lines kept). The pnpm scripts log lint and typecheck errors. Test runners log through
their own hooks (`apps/backend/conftest.py`, the Vitest and Playwright reporters), so a direct
`uv run pytest` or `vitest` run counts too. Nothing is logged in CI. Lines are tab separated:

```
2026-10-10T00:55:27+02:00  main@cb9dbf3  typecheck  frontend  src/app/page.tsx:12:7  TS2322 Type 'string' is not assignable…
```

`CHECK_FAILURES_DISABLE=1` turns it off, and `CHECK_FAILURES_LOG=<path>` redirects it. The code
is in `scripts/check-failures/`, tested by `node --test 'scripts/check-failures/*.test.mjs'`.

## Docs
- [Rebrand guide](docs/rebrand-guide.md) — change the look in 3 edits
- [Env matrix](docs/env-matrix.md) · [Data handling / GDPR](docs/gdpr-data-handling.md)
- `CLAUDE.md` — conventions every contributor follows

## Build status

Repo is green: `turbo typecheck lint` (8/8), API `pytest` (11/11).

**Done**
- Monorepo + design system (constrained light/dark tokens, single rebrand surface)
- Web (ixartz fork, Clerk removed) + branded dashboard shell (sidebar/topbar, light/dark)
- API (FastAPI, async SQLAlchemy, Alembic) + JWKS auth (`Principal`, `require_role`)
- Better Auth (email+password, org + JWT/JWKS; Entra gated on env)
- Typed client (Hey API) generated from the API's OpenAPI
- Local onboarding (`pnpm dev:stack` — Docker Postgres)
- **Document → AI flow**: upload → extract → analyze → result, tenant-scoped
  (Azure Blob/Docling/Document Intelligence/Foundry gated; local fallbacks)
- Security: role-gated endpoint + tests, gitleaks config, GDPR notes
- Docs: fork-per-client runbook, rebrand guide, env matrix, ADRs, bootstrap script

- Infra (Bicep, EU) — compiles clean · CI/CD (GitHub Actions: CI gates, manual Infra, CD deploy)
- Secrets via Key Vault + managed identity · observability (Sentry/OTel) + email (ACS/Resend)
- Design system: assemble-not-build (TanStack table, charts, one-line theme presets)

**Remaining**
- Live auth loop against a real Postgres (code done; needs a DB to run once)
- Deploy verification on a real Azure subscription (Docker builds + a manual Infra run, then CD)
- Optional, per-mission: Stripe billing
