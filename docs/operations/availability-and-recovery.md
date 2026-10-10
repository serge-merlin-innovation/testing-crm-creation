# Availability, recovery and security operations (NFR-01, NFR-03)

Ticket #20. What runs automatically, what an operator does, and where each result is logged.
Nothing here is deployed without the user's say-so: the Infra workflow applies `infra/` only when started by hand.

## Targets

| Requirement | Target | Enforced by |
| --- | --- | --- |
| NFR-03 c1 uptime | 99.5% each month between 08:00 and 20:00 Brussels time | `infra/uptime-monitor.bicep`: probe of `/health/ready` every 5 min from 5 EU locations, alerts when 2 locations fail or hourly availability drops under 99.5% |
| NFR-03 c2 RPO | at most 24 h of data lost | Daily automated PostgreSQL backups plus continuous WAL (point-in-time restore), 35 days, geo-redundant to the paired EU region (`infra/parameters/postgres-server.bicepparam`) |
| NFR-03 c2 RTO | service back within 8 h | The drill below, logged at `POST /api/v1/operations/recovery-drills` (fails when over 8 h) |
| NFR-03 c3 maintenance | 48 h notice, outside business hours | `POST /api/v1/operations/maintenance-windows` refuses less than 48 h notice or any minute inside 08:00-20:00 Mon-Fri, then notifies every user in their language. Azure's own PostgreSQL window is Sunday 02:00 UTC |
| NFR-01 c1 TLS / encryption | TLS 1.2+, AES-256 at rest | `require_secure_transport`, `ssl_min_protocol_version=TLSv1.2`, storage `minimumTlsVersion`, container apps `allowInsecure=false`; Azure service-managed AES-256 for PostgreSQL, backups and storage (infrastructure encryption on) |
| NFR-01 c2 EU only | data and backups in EU data centres | Every template's `location` is restricted to EU regions; geo-backup pairs stay in the EU |
| NFR-01 c3 OWASP | no open high or critical finding at release | CI job `owasp-zap` (fails on High), `GET /api/v1/operations/release-gate` |
| NFR-01 c4 pentest | high/critical fixed within 30 days | `POST /api/v1/operations/security-findings` sets the due date, hourly job alerts admins and compliance once overdue |
| NFR-01 c5 restore test | daily backups kept 35 days, quarterly restore logged | `GET /api/v1/operations/recovery-drills/status` says when the quarterly test is due |

All of these are covered by `apps/backend/tests/unit/infrastructure/test_hosting_contract.py` and `apps/backend/tests/integration/operations/`.

## Measuring business-hours availability (monthly)

Run in the Application Insights workspace created by `uptime-monitor.bicep`:

```kusto
availabilityResults
| where timestamp > startofmonth(now(), -1) and timestamp < startofmonth(now())
| extend local = datetime_utc_to_local(timestamp, 'Europe/Brussels')
| where dayofweek(local) between (1d .. 5d) and hourofday(local) between (8 .. 19)
| summarize availability = 100.0 * countif(success == 1) / count()
```

Record the figure in the monthly operations report. Below 99.5%: open a finding (`source: other`, severity high) so it is tracked to closure.

## Quarterly restore test (NFR-01 c5) and disaster drill (NFR-03 c2)

1. Pick the latest automated backup time (Azure portal, server, Backup and restore). Note it as `backup_taken_at`.
2. Note the start time (`started_at`). Restore to a new server: `az postgres flexible-server restore --source-server <prod> --name <scratch> --restore-time <backup time>` in the same EU region. For the disaster drill use `geo-restore` to the paired region instead.
3. Point a staging copy of the backend at the scratch server, run `uv run alembic current` and the smoke checks: sign in, open a deal, search a contact, run the dashboard report.
4. Compare row counts of `contacts`, `companies`, `mandates`, `audit_log` with production at the backup time.
5. Note when the staging app answers `/health/ready` with 200 (`service_restored_at`).
6. Log it: `POST /api/v1/operations/recovery-drills` with `kind` `restore_test` or `disaster_recovery`, the three times, `data_verified` and notes. The API computes RPO and RTO and marks the drill passed or failed. The entry is in the audit log.
7. Delete the scratch server.

## Planned maintenance

1. At least 48 hours ahead, an admin posts the window to `POST /api/v1/operations/maintenance-windows`. Windows touching 08:00-20:00 on a weekday are refused.
2. Every active user gets the notice in-app and by email in their language; `GET /api/v1/operations/maintenance-windows/upcoming` lists it.

## Penetration test findings

1. Enter each finding from the yearly test at `POST /api/v1/operations/security-findings` (`source: pentest`). High and critical are due 30 days after `reported_at`.
2. Mark fixed with `PATCH /api/v1/operations/security-findings/{id}` once the fix is released; the response says whether it was fixed in time.
3. Overdue findings notify admins and compliance once. The release gate stays closed while any high or critical finding is open.
