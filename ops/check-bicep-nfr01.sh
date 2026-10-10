#!/usr/bin/env bash
# NFR-01 static assertions on infra/: TLS 1.2+, no plain HTTP, EU region, 35-day backups. Reads Bicep only: builds locally with `az bicep build`, deploys nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

failures=0
fail() { echo "FAIL: $*" >&2; failures=$((failures + 1)); }

for template in infra/frontend-container-app.bicep infra/backend-container-app.bicep; do
  grep -q "param allowInsecure bool = false" "$template" || fail "$template allows plain HTTP by default"
done
for parameters in infra/parameters/frontend-container-app.bicepparam infra/parameters/backend-container-app.bicepparam; do
  grep -q "param allowInsecure = false" "$parameters" || fail "$parameters allows plain HTTP"
done
grep -q "param minimumTlsVersion = 'TLS1_2'" infra/parameters/storage-account.bicepparam || fail "storage accepts TLS < 1.2"

backup_days="$(sed -n "s/^param backupRetentionDays = \([0-9]*\)/\1/p" infra/parameters/postgres-server.bicepparam)"
[[ "${backup_days:-0}" -ge 35 ]] || fail "PostgreSQL keeps backups ${backup_days:-?} days; NFR-01 needs 35"

eu_regions='^(westeurope|northeurope|francecentral|francesouth|germanywestcentral|germanynorth|swedencentral|swedensouth|italynorth|polandcentral|spaincentral|belgiumcentral|norwayeast|switzerlandnorth|austriaeast)$'
if [[ -n "${AZURE_LOCATION:-}" ]]; then
  [[ "$AZURE_LOCATION" =~ $eu_regions ]] || fail "AZURE_LOCATION $AZURE_LOCATION is not an EU region"
else
  echo "note: AZURE_LOCATION not set, EU-region check skipped (set it to the Infra workflow's value)"
fi

if command -v az >/dev/null; then
  for template in infra/*.bicep; do az bicep build --file "$template" --stdout >/dev/null || fail "$template does not build"; done
fi

[[ "$failures" -eq 0 ]] && echo "NFR-01 Bicep assertions passed" || exit 1
