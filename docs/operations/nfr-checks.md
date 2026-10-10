# Operational checks (NFR-01, NFR-02, NFR-03)

The spec's Seam 3 checks. The automated ones live in `.github/workflows/operational-checks.yml`. That workflow is manual only, and it runs against a Postgres service container and an app started inside the runner. It never runs against a deployed environment. The rest is a release checklist.

## Automated

| Check | Criterion | How |
| --- | --- | --- |
| TLS 1.2+, no plain HTTP, 35-day backups, EU region | NFR-01 c1, c2, c5 | `ops/check-bicep-nfr01.sh` asserts the Bicep and its parameters. Set `AZURE_LOCATION` to the Infra workflow's value so the EU check runs. |
| OWASP Top 10 baseline, no high findings | NFR-01 c3 | ZAP baseline job, rules in `ops/zap/rules.tsv` |
| 50 users, 200k contacts: p95 page < 2 s, search < 1 s, all-deals report < 10 s | NFR-02 c1, c2 | `scripts.seed_load_data` then `ops/load/nfr02.k6.js`. Both refuse any host that is not local. |
| Committed OpenAPI matches the app | Testing Decisions | `test_public_api_contract.py` |
| TOTP secrets encrypted at rest | NFR-01 c1 | `test_totp_secret_is_encrypted_at_rest`. The key is `TOTP_ENCRYPTION_KEY` in Key Vault. |

Run the load test locally on a throwaway database. Never use port 5432:

```bash
docker run -d --rm --name crm-load-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=crm -p 55611:5432 postgres:16-alpine
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55611/crm
cd apps/backend && uv run alembic upgrade head && uv run python -m scripts.setup_initial_data
TOKENS=$(uv run python -m scripts.seed_load_data --contacts 200000 | tail -1)
uv run fastapi run src/interfaces/main.py --port 8611 &
cd ../.. && BASE_URL=http://localhost:8611 API_TOKENS=$TOKENS k6 run ops/load/nfr02.k6.js
```

## Release checklist (manual, record the result in the release notes)

- [ ] NFR-01 c1: Azure Database for PostgreSQL and Storage encrypt at rest with AES-256 (platform default; confirm no customer-managed key was disabled).
- [ ] NFR-01 c4: the yearly penetration test report is filed. Every high or critical finding has a fix date within 30 days.
- [ ] NFR-01 c5: the quarterly restore test restored the latest backup into a scratch server. Log the date, backup timestamp and row counts.
- [ ] NFR-03 c1: the uptime monitor (Azure Monitor availability test on `/health`, 08:00-20:00 CET) shows at least 99.5% for the month.
- [ ] NFR-03 c2: the RPO/RTO drill is done. The point-in-time restore lost at most 24 h of data and service was back within 8 h.
- [ ] NFR-03 c3: planned maintenance was announced to users 48 h ahead and scheduled outside 08:00-20:00 CET.
