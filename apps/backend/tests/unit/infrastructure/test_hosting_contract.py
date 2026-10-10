"""The production hosting contract (NFR-01, NFR-03), read from the Bicep in `infra/`.

Nothing here talks to Azure: it pins what the checked-in templates would deploy, so a change that
weakens TLS, encryption, data residency, backup retention or uptime monitoring fails the build.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

INFRA = Path(__file__).parents[5] / "infra"
PARAMETERS = INFRA / "parameters"
WORKFLOWS = INFRA.parent / ".github" / "workflows"

EU_REGIONS = {
    "westeurope",
    "northeurope",
    "francecentral",
    "francesouth",
    "germanywestcentral",
    "germanynorth",
    "swedencentral",
    "swedensouth",
    "italynorth",
    "polandcentral",
    "spaincentral",
    "belgiumcentral",
    "austriaeast",
}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def param_value(file: Path, name: str) -> str:
    match = re.search(rf"^param {name} = (.+)$", text(file), re.MULTILINE)
    assert match, f"{file.name} does not set {name}"
    return match.group(1).strip()


def templates_with_location() -> list[Path]:
    return sorted(path for path in INFRA.glob("*.bicep") if re.search(r"^param location string", text(path), re.MULTILINE))


def allowed_values(template: Path, name: str) -> set[str]:
    match = re.search(rf"@allowed\(\s*\[([^\]]*)\]\s*\)\s*param {name} ", text(template))
    assert match, f"{template.name} does not restrict {name} with @allowed"
    return set(re.findall(r"'([^']+)'", match.group(1)))


class TestDataResidency:
    @pytest.mark.parametrize("template", templates_with_location(), ids=lambda path: path.name)
    def test_every_resource_location_is_an_eu_region(self, template: Path):
        regions = allowed_values(template, "location")
        assert regions, template.name
        assert regions <= EU_REGIONS, regions - EU_REGIONS

    def test_backups_stay_in_the_eu(self):
        # Geo-redundant backups go to the paired region, which for every allowed region is also in the EU.
        server = PARAMETERS / "postgres-server.bicepparam"
        assert param_value(server, "geoRedundantBackup") == "'Enabled'"


class TestEncryption:
    def test_postgres_accepts_tls_1_2_or_newer_only(self):
        configurations = text(PARAMETERS / "postgres-server.bicepparam")
        assert re.search(r"name: 'require_secure_transport', value: 'ON'", configurations)
        assert re.search(r"name: 'ssl_min_protocol_version', value: 'TLSv1.2'", configurations)

    def test_storage_accepts_tls_1_2_or_newer_and_https_only(self):
        assert allowed_values(INFRA / "storage-account.bicep", "minimumTlsVersion") <= {"TLS1_2", "TLS1_3"}
        assert param_value(PARAMETERS / "storage-account.bicepparam", "minimumTlsVersion") in ("'TLS1_2'", "'TLS1_3'")
        assert "supportsHttpsTrafficOnly: true" in text(INFRA / "storage-account.bicep")

    @pytest.mark.parametrize("app", ["backend", "frontend"])
    def test_container_apps_refuse_plain_http(self, app: str):
        template = text(INFRA / f"{app}-container-app.bicep")
        assert re.search(r"^param allowInsecure bool = false$", template, re.MULTILINE)
        assert "@allowed([\n  false\n])\nparam allowInsecure" in template

    def test_storage_encrypts_at_rest_with_aes_256(self):
        template = text(INFRA / "storage-account.bicep")
        assert "keySource: 'Microsoft.Storage'" in template
        for service in ("blob", "file", "queue", "table"):
            assert re.search(rf"{service}: \{{\s*enabled: true", template), service

    def test_postgres_storage_is_encrypted_with_service_managed_keys(self):
        # Azure Database for PostgreSQL encrypts storage and backups with AES-256 service-managed keys;
        # the template must not opt into a customer-managed key path that could be left unset.
        template = text(INFRA / "postgres-server.bicep")
        assert "dataEncryption: {\n      type: 'SystemManaged'\n    }" in template


class TestBackups:
    def test_postgres_keeps_daily_backups_35_days(self):
        assert param_value(PARAMETERS / "postgres-server.bicepparam", "backupRetentionDays") == "35"

    def test_blob_soft_delete_matches_the_backup_window(self):
        assert param_value(PARAMETERS / "blob-service.bicepparam", "softDeleteRetentionDays") == "35"

    def test_maintenance_runs_outside_business_hours(self):
        server = PARAMETERS / "postgres-server.bicepparam"
        assert param_value(server, "customMaintenanceWindow") == "'Enabled'"
        # Sunday (0) at 02:00 UTC = 03:00 or 04:00 in Brussels, never inside 8:00-20:00.
        assert param_value(server, "maintenanceDayOfWeek") == "0"
        assert int(param_value(server, "maintenanceStartHour")) < 5


class TestUptimeMonitoring:
    def test_an_availability_test_probes_the_health_endpoint_from_eu_locations(self):
        template = text(INFRA / "uptime-monitor.bicep")
        assert "Microsoft.Insights/webtests" in template
        assert "/health/ready" in text(PARAMETERS / "uptime-monitor.bicepparam")
        assert allowed_values(INFRA / "uptime-monitor.bicep", "location") <= EU_REGIONS
        assert "emea-nl-ams-azr" in template

    def test_an_alert_fires_when_the_probe_fails(self):
        template = text(INFRA / "uptime-monitor.bicep")
        assert "Microsoft.Insights/metricAlerts" in template
        assert "availabilityResults/availabilityPercentage" in template
        assert "Microsoft.Insights/actionGroups" in template

    def test_the_monitor_is_validated_and_deployable_from_the_infra_workflow(self):
        workflow = text(WORKFLOWS / "infra.yml")
        assert "infra/uptime-monitor.bicep" in workflow
        assert "infra/parameters/uptime-monitor.bicepparam" in workflow


@pytest.mark.skipif(shutil.which("az") is None, reason="Azure CLI not installed")
@pytest.mark.parametrize(
    "template", ["postgres-server.bicep", "storage-account.bicep", "uptime-monitor.bicep", "backend-container-app.bicep"]
)
def test_templates_compile(template: str):
    result = subprocess.run(
        ["az", "bicep", "build", "--file", str(INFRA / template), "--stdout", "--only-show-errors"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


class TestReleaseGates:
    """NFR-01 c3 and NFR-02 c1 run in CI and block a release."""

    def workflow(self) -> dict:
        return yaml.safe_load(text(WORKFLOWS / "ci.yml"))

    def test_an_owasp_zap_baseline_blocks_high_or_critical_findings(self):
        jobs = self.workflow()["jobs"]
        steps = jobs["owasp-zap"]["steps"]
        assert any(str(step.get("uses", "")).startswith("zaproxy/action-baseline") for step in steps)
        assert any("riskcode | tonumber) >= 3" in step.get("run", "") for step in steps)
        assert "owasp-zap" in jobs["version"]["needs"]

    def test_the_k6_load_test_runs_50_users_on_200k_contacts_and_gates_the_release(self):
        jobs = self.workflow()["jobs"]
        assert "load-test" in jobs["version"]["needs"]
        assert jobs["load-test"]["uses"] == "./.github/workflows/load-test.yml"
        load_test = yaml.safe_load(text(WORKFLOWS / "load-test.yml"))
        triggers = load_test[True]  # PyYAML reads the bare `on:` key as the boolean True.
        assert triggers["pull_request"]["paths"] == ["apps/backend/src/**"]
        assert "workflow_call" in triggers
        assert any(step.get("run", "").startswith("k6 run") for step in load_test["jobs"]["load-test"]["steps"])
        script = text(INFRA.parent / "apps" / "backend" / "perf" / "k6" / "load.js")
        assert "vus: 50" in script
        assert '"http_req_duration{kind:page}": ["p(95)<2000"]' in script
        assert '"http_req_duration{kind:search}": ["p(95)<1000"]' in script
        seed = text(INFRA.parent / "apps" / "backend" / "scripts" / "load_dataset.py")
        assert "contacts: int = 200_000" in seed
        assert "users: int = 50" in seed


def test_the_recovery_runbook_states_rpo_rto_and_how_drills_are_logged():
    runbook = text(INFRA.parent / "docs" / "operations" / "availability-and-recovery.md")
    for needle in ("24 h", "8 h", "99.5%", "/api/v1/operations/recovery-drills", "48 h", "30 days", "35 days"):
        assert needle in runbook, needle
