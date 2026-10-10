from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.auth.clocked_sessions import set_session_clock
from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.role.permissions import RoleName
from tests.integration.foundation.helpers import login, make_user

pytestmark = pytest.mark.asyncio

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
PHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


@pytest.fixture
def clock():
    frozen = FrozenClock(NOW)
    set_clock(frozen)
    set_session_clock(frozen)
    yield frozen
    set_clock(SystemClock())
    set_session_clock(SystemClock())


def browser(user_agent: str = DESKTOP) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 50000)),
        base_url="http://test",
        headers={"user-agent": user_agent},
    )


async def me(client: AsyncClient) -> int:
    return (await client.get("/api/v1/users/me")).status_code


# AUTH-03 c1: 30 idle minutes end the session; the next act is refused so the client re-authenticates.
async def test_desktop_session_expires_after_30_idle_minutes(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        await login(tab, "ana@firm.be")
        clock.advance(timedelta(minutes=29))
        assert await me(tab) == 200
        clock.advance(timedelta(minutes=29))
        assert await me(tab) == 200
        clock.advance(timedelta(minutes=30, seconds=1))
        assert await me(tab) == 401


# AUTH-03 c2: the client learns when the idle window closes, without the check itself counting as activity.
async def test_session_status_reports_expiry_without_extending_it(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        await login(tab, "ana@firm.be")
        clock.advance(timedelta(minutes=28))
        status = (await tab.get("/api/v1/auth/session")).json()
        assert datetime.fromisoformat(status["idle_expires_at"]) == NOW + timedelta(minutes=30)
        assert datetime.fromisoformat(status["absolute_expires_at"]) == NOW + timedelta(hours=12)
        assert status["warning_seconds"] == 120
        clock.advance(timedelta(minutes=2, seconds=1))
        assert (await tab.get("/api/v1/auth/session")).status_code == 401


# AUTH-03 c2 / c6: Stay logged in renews the session silently, returning the new expiry.
async def test_stay_logged_in_renews_the_idle_window(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        csrf = await login(tab, "ana@firm.be")
        clock.advance(timedelta(minutes=29))
        renewed = await tab.post("/api/v1/auth/session/renew", headers=csrf)
        assert renewed.status_code == 200
        assert datetime.fromisoformat(renewed.json()["idle_expires_at"]) == clock.now() + timedelta(minutes=30)
        clock.advance(timedelta(minutes=29))
        assert await me(tab) == 200


# AUTH-03 c3: 12 hours after login, re-authentication is required however busy the user is.
async def test_absolute_lifetime_of_12_hours_ends_an_active_session(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        await login(tab, "ana@firm.be")
        for _ in range(47):
            clock.advance(timedelta(minutes=15))
            assert await me(tab) == 200
        clock.advance(timedelta(minutes=15))
        assert await me(tab) == 401


# AUTH-03 c4: two tabs share one server session, so activity in one keeps the other alive.
async def test_activity_in_one_tab_keeps_the_other_tab_alive(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as first:
        await login(first, "ana@firm.be")
        async with browser() as second:
            second.cookies = first.cookies
            for _ in range(4):
                clock.advance(timedelta(minutes=20))
                assert await me(first) == 200
            status = (await second.get("/api/v1/auth/session")).json()
            assert datetime.fromisoformat(status["idle_expires_at"]) == clock.now() + timedelta(minutes=30)
            assert await me(second) == 200


# AUTH-03 c5: an admin's new timeouts apply to sessions opened afterwards, not to live ones.
async def test_admin_timeout_change_applies_to_new_sessions_only(client, seeded_db, clock):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as admin, browser() as before, browser() as after:
        admin_csrf = await login(admin, "admin@firm.be")
        await login(before, "ana@firm.be")

        changed = await admin.put(
            "/api/v1/sessions/policy",
            json={"desktop_idle_minutes": 10, "mobile_idle_minutes": 5, "absolute_hours": 8, "mobile_read_only": False},
            headers=admin_csrf,
        )
        assert changed.status_code == 200, changed.text
        assert (await admin.get("/api/v1/sessions/policy")).json()["desktop_idle_minutes"] == 10

        await login(after, "ana@firm.be")
        clock.advance(timedelta(minutes=11))
        assert await me(before) == 200
        assert await me(after) == 401

    entries = (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "session.policy_changed"))).scalars()
    assert len(list(entries)) == 1


async def test_only_settings_managers_change_the_session_policy(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        csrf = await login(tab, "ana@firm.be")
        refused = await tab.put(
            "/api/v1/sessions/policy",
            json={"desktop_idle_minutes": 600, "mobile_idle_minutes": 5, "absolute_hours": 8, "mobile_read_only": False},
            headers=csrf,
        )
        assert refused.status_code == 403


async def test_policy_rejects_a_mobile_timeout_longer_than_desktop(client, seeded_db, clock):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    async with browser() as admin:
        csrf = await login(admin, "admin@firm.be")
        response = await admin.put(
            "/api/v1/sessions/policy",
            json={"desktop_idle_minutes": 10, "mobile_idle_minutes": 20, "absolute_hours": 8, "mobile_read_only": False},
            headers=csrf,
        )
        assert response.status_code == 422


# AUTH-04 c1: Log out revokes the server-side session; the cookie no longer opens anything.
async def test_logout_revokes_the_server_session(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        csrf = await login(tab, "ana@firm.be")
        stolen = dict(tab.cookies)
        assert (await tab.post("/api/v1/auth/logout", headers=csrf)).status_code == 200
        async with browser() as attacker:
            attacker.cookies.update(stolen)
            assert await me(attacker) == 401


# AUTH-04 c2: authenticated API answers are never stored, so Back cannot replay a deal page.
async def test_authenticated_responses_are_not_cacheable(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as tab:
        await login(tab, "ana@firm.be")
        response = await tab.get("/api/v1/users/me")
        assert "no-store" in response.headers["cache-control"]


# AUTH-04 c3 / AUTH-07 c3: Log out everywhere ends every session of the user, on every device.
async def test_logout_everywhere_ends_all_my_sessions(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await make_user(seeded_db, "bob@firm.be", RoleName.ANALYST)
    async with browser() as laptop, browser(PHONE) as phone, browser() as colleague:
        csrf = await login(laptop, "ana@firm.be")
        await login(phone, "ana@firm.be")
        await login(colleague, "bob@firm.be")

        response = await laptop.post("/api/v1/auth/logout-everywhere", headers=csrf)

        assert response.status_code == 200
        assert response.json()["revoked"] == 2
        assert await me(laptop) == 401
        assert await me(phone) == 401
        assert await me(colleague) == 200

    entries = (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "logout.everywhere"))).scalars()
    assert len(list(entries)) == 1


# AUTH-07 c3: an admin ends every session of a user who lost their phone.
async def test_admin_logs_a_user_out_everywhere(client, seeded_db: AsyncSession, clock):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser() as admin, browser(PHONE) as phone, browser() as other:
        admin_csrf = await login(admin, "admin@firm.be")
        await login(phone, "ana@firm.be")
        other_csrf = await login(other, "ana@firm.be")

        assert (await other.delete(f"/api/v1/users/{ana['id'] + 0}/sessions", headers=other_csrf)).status_code == 403
        response = await admin.delete(f"/api/v1/users/{ana['id']}/sessions", headers=admin_csrf)

        assert response.status_code == 200
        assert await me(phone) == 401
        assert await me(admin) == 200


# AUTH-07 c1: a phone browser logs in with password and code and gets a working session.
async def test_phone_logs_in_with_password_and_code(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser(PHONE) as phone:
        await login(phone, "ana@firm.be")
        assert await me(phone) == 200
        assert (await phone.get("/api/v1/auth/session")).json()["mobile"] is True


# AUTH-07 c4: a mobile session times out after 15 idle minutes, sooner than desktop.
async def test_mobile_session_times_out_after_15_idle_minutes(client, seeded_db, clock):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with browser(PHONE) as phone, browser() as laptop:
        await login(phone, "ana@firm.be")
        await login(laptop, "ana@firm.be")
        clock.advance(timedelta(minutes=15, seconds=1))
        assert await me(phone) == 401
        assert await me(laptop) == 200


# AUTH-07 c2: the read-only mobile setting reaches the client so it can hide edit and export actions.
async def test_mobile_read_only_setting_reaches_every_session(client, seeded_db, clock):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    async with browser() as admin:
        csrf = await login(admin, "admin@firm.be")
        assert (await admin.get("/api/v1/auth/session")).json()["mobile_read_only"] is False
        await admin.put(
            "/api/v1/sessions/policy",
            json={"desktop_idle_minutes": 30, "mobile_idle_minutes": 15, "absolute_hours": 12, "mobile_read_only": True},
            headers=csrf,
        )
        assert (await admin.get("/api/v1/auth/session")).json()["mobile_read_only"] is True
