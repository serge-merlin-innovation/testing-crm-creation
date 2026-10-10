"""NFR-01 c4/c5 and NFR-03: readiness probe, recovery drills, security findings, maintenance notices."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.database.session import async_session
from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.notification.models import Notification
from src.modules.operations.jobs import overdue_findings
from src.modules.role.permissions import RoleName
from tests.integration.crm.deal_helpers import build_world

pytestmark = pytest.mark.asyncio

# Saturday 10 October 2026, 11:00 Brussels.
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def world(client, seeded_db):
    clock = FrozenClock(NOW)
    set_clock(clock)
    built = await build_world(seeded_db)
    built.clock = clock
    built.admin = await built.actor("ops", RoleName.ADMIN)
    built.compliance = await built.actor("carla", RoleName.COMPLIANCE)
    built.partner = await built.actor("paula", RoleName.PARTNER)
    yield built
    for session in built.clients:
        await session.aclose()
    set_clock(SystemClock())


async def post(actor, path, body):
    return await actor.client.post(path, json=body, headers=actor.headers)


async def audit_actions(db, record_type):
    rows = await db.execute(select(AuditEntry.action).where(AuditEntry.record_type == record_type))
    return [row for (row,) in rows]


class TestReadiness:
    async def test_ready_checks_the_database(self, client):
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "database": "ok"}

    async def test_ready_reports_503_when_the_database_is_down(self, client):
        class Broken:
            async def execute(self, *_args, **_kwargs):
                raise ConnectionError("down")

        async def broken():
            yield Broken()

        app.dependency_overrides[async_session] = broken
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["database"] == "unavailable"


class TestRecoveryDrills:
    """NFR-01 c5 (quarterly restore test, logged) and NFR-03 c2 (RPO 24 h, RTO 8 h)."""

    async def test_a_restore_test_within_rpo_and_rto_is_logged_as_passed(self, world):
        response = await post(
            world.admin,
            "/api/v1/operations/recovery-drills",
            {
                "kind": "restore_test",
                "backup_taken_at": (NOW - timedelta(hours=20)).isoformat(),
                "started_at": (NOW - timedelta(hours=3)).isoformat(),
                "service_restored_at": (NOW - timedelta(hours=1)).isoformat(),
                "data_verified": True,
                "notes": "Restored the 06:00 backup into a scratch server; row counts match.",
            },
        )
        assert response.status_code == 201, response.text
        drill = response.json()
        assert drill["data_loss_hours"] == 17.0
        assert drill["recovery_hours"] == 2.0
        assert drill["passed"] is True
        assert "recovery_drill.logged" in await audit_actions(world.db, "recovery_drill")

    async def test_a_drill_that_breaks_rpo_or_rto_fails(self, world):
        response = await post(
            world.admin,
            "/api/v1/operations/recovery-drills",
            {
                "kind": "disaster_recovery",
                "backup_taken_at": (NOW - timedelta(hours=40)).isoformat(),
                "started_at": (NOW - timedelta(hours=10)).isoformat(),
                "service_restored_at": NOW.isoformat(),
                "data_verified": True,
            },
        )
        drill = response.json()
        assert drill["passed"] is False
        assert set(drill["failures"]) == {"rpo", "rto"}

    async def test_status_flags_a_quarter_without_a_passed_restore_test(self, world):
        status = (await world.admin.client.get("/api/v1/operations/recovery-drills/status")).json()
        assert status == {"restore_test_due": True, "last_passed_at": None, "rpo_hours": 24, "rto_hours": 8}

        await post(
            world.admin,
            "/api/v1/operations/recovery-drills",
            {
                "kind": "restore_test",
                "backup_taken_at": (NOW - timedelta(hours=5)).isoformat(),
                "started_at": (NOW - timedelta(hours=2)).isoformat(),
                "service_restored_at": (NOW - timedelta(hours=1)).isoformat(),
                "data_verified": True,
            },
        )
        status = (await world.admin.client.get("/api/v1/operations/recovery-drills/status")).json()
        assert status["restore_test_due"] is False

        world.clock.set(NOW + timedelta(days=93))
        status = (await world.admin.client.get("/api/v1/operations/recovery-drills/status")).json()
        assert status["restore_test_due"] is True

    async def test_only_settings_managers_log_drills(self, world):
        response = await post(
            world.partner,
            "/api/v1/operations/recovery-drills",
            {
                "kind": "restore_test",
                "backup_taken_at": NOW.isoformat(),
                "started_at": NOW.isoformat(),
                "service_restored_at": NOW.isoformat(),
                "data_verified": True,
            },
        )
        assert response.status_code == 403


class TestSecurityFindings:
    """NFR-01 c3/c4: high or critical findings are fixed within 30 days, and block a release."""

    async def test_a_high_finding_is_due_in_30_days_and_blocks_release_until_fixed(self, world):
        response = await post(
            world.admin,
            "/api/v1/operations/security-findings",
            {"source": "pentest", "severity": "high", "title": "Stored XSS in note body", "reference": "PT-2026-07"},
        )
        assert response.status_code == 201, response.text
        finding = response.json()
        assert finding["due_at"].startswith("2026-11-09")
        gate = (await world.admin.client.get("/api/v1/operations/release-gate")).json()
        assert gate == {"releasable": False, "open_blocking": 1, "overdue": 0}

        fixed = await world.admin.client.patch(
            f"/api/v1/operations/security-findings/{finding['id']}",
            json={"status": "fixed"},
            headers=world.admin.headers,
        )
        assert fixed.json()["fixed_at"] is not None
        assert fixed.json()["fixed_in_time"] is True
        gate = (await world.admin.client.get("/api/v1/operations/release-gate")).json()
        assert gate["releasable"] is True
        assert await audit_actions(world.db, "security_finding") == ["security_finding.created", "security_finding.updated"]

    async def test_medium_findings_do_not_block(self, world):
        await post(world.admin, "/api/v1/operations/security-findings", {"source": "zap", "severity": "medium", "title": "x"})
        gate = (await world.admin.client.get("/api/v1/operations/release-gate")).json()
        assert gate["releasable"] is True

    async def test_overdue_findings_alert_admins_and_compliance_once(self, world):
        await post(
            world.admin, "/api/v1/operations/security-findings", {"source": "pentest", "severity": "critical", "title": "RCE"}
        )
        world.clock.set(NOW + timedelta(days=31))
        await overdue_findings(world.db, world.clock.now())
        await overdue_findings(world.db, world.clock.now())
        rows = (
            await world.db.execute(select(Notification.user_id).where(Notification.kind == "security.finding_overdue"))
        ).all()
        assert sorted(user_id for (user_id,) in rows) == sorted([world.admin.id, world.compliance.id])
        gate = (await world.admin.client.get("/api/v1/operations/release-gate")).json()
        assert gate["overdue"] == 1


class TestMaintenanceWindows:
    """NFR-03 c3: notice 48 hours ahead, outside 8:00-20:00 Brussels time on working days."""

    async def test_announcing_under_48_hours_ahead_is_refused(self, world):
        response = await post(
            world.admin,
            "/api/v1/operations/maintenance-windows",
            {"starts_at": "2026-10-11T22:00:00+02:00", "ends_at": "2026-10-12T01:00:00+02:00", "reason": "Upgrade"},
        )
        assert response.status_code == 422
        assert "48 hours" in response.json()["detail"]

    async def test_a_window_inside_business_hours_is_refused(self, world):
        response = await post(
            world.admin,
            "/api/v1/operations/maintenance-windows",
            {"starts_at": "2026-10-14T19:00:00+02:00", "ends_at": "2026-10-14T21:00:00+02:00", "reason": "Upgrade"},
        )
        assert response.status_code == 422
        assert "8:00" in response.json()["detail"]

    async def test_a_valid_window_notifies_every_active_user_and_is_listed(self, world):
        response = await post(
            world.admin,
            "/api/v1/operations/maintenance-windows",
            {"starts_at": "2026-10-14T21:00:00+02:00", "ends_at": "2026-10-15T02:00:00+02:00", "reason": "Database upgrade"},
        )
        assert response.status_code == 201, response.text
        rows = (await world.db.execute(select(Notification.user_id).where(Notification.kind == "maintenance.scheduled"))).all()
        assert len(rows) == 3
        assert len([email for email in world.emails.sent if "14/10/2026" in email.body]) == 3
        upcoming = (await world.partner.client.get("/api/v1/operations/maintenance-windows/upcoming")).json()
        assert [window["reason"] for window in upcoming] == ["Database upgrade"]
        assert "maintenance.scheduled" in await audit_actions(world.db, "maintenance_window")

    async def test_the_notice_is_in_each_users_language(self, world):
        await world.compliance.client.patch(
            f"/api/v1/users/{world.compliance.id}", json={"language": "nl"}, headers=world.compliance.headers
        )
        await post(
            world.admin,
            "/api/v1/operations/maintenance-windows",
            {"starts_at": "2026-10-14T21:00:00+02:00", "ends_at": "2026-10-15T02:00:00+02:00", "reason": "Upgrade"},
        )
        dutch = [email for email in world.emails.sent if email.to == world.compliance.email]
        assert dutch
        assert dutch[0].subject.startswith("Gepland onderhoud")
