from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.email import InMemoryEmailSender, LoggingEmailSender, set_email_sender
from src.infrastructure.geoip import StaticGeoIp, UnknownGeoIp, set_geoip
from src.interfaces.main import app
from src.modules.audit.models import AuditEntry
from src.modules.role.permissions import RoleName
from src.modules.security import service as security_service
from src.modules.security.dependencies import StepUpUserDep
from src.modules.security.totp import totp_code
from tests.integration.foundation.helpers import PASSWORD, TOTP_SECRETS, current_code, login, make_user, start_login

pytestmark = pytest.mark.asyncio

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
OTHER_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


@pytest.fixture
def clock():
    frozen = FrozenClock(NOW)
    set_clock(frozen)
    yield frozen
    set_clock(SystemClock())


@pytest.fixture
def mailbox():
    sender = InMemoryEmailSender()
    set_email_sender(sender)
    yield sender
    set_email_sender(LoggingEmailSender())


@pytest.fixture
def geo():
    fake = StaticGeoIp()
    set_geoip(fake)
    yield fake
    set_geoip(UnknownGeoIp())


def second_client(client: AsyncClient, user_agent: str = BROWSER, ip: str = "127.0.0.1") -> AsyncClient:
    transport = ASGITransport(app=app, client=(ip, 50000))
    return AsyncClient(transport=transport, base_url="http://test", headers={"user-agent": user_agent})


async def actions(db: AsyncSession, action: str) -> list[AuditEntry]:
    return list((await db.execute(select(AuditEntry).where(AuditEntry.action == action))).scalars().all())


async def submit_code(client: AsyncClient, challenge: str, code: str, trust: bool = False):
    return await client.post(
        "/api/v1/auth/login/second-factor", json={"challenge": challenge, "code": code, "trust_device": trust}
    )


# AUTH-01 c2 / AUTH-02 c1: correct password asks for the second factor before any session exists;
# a first login must enrol by QR code and confirm a code.
async def test_first_login_enrols_totp_by_qr_before_a_session_exists(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    body = await start_login(client, "ana@firm.be")

    assert body["step"] == "enrol"
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["qr_svg"].lstrip().startswith("<svg")
    assert "session_id" not in client.cookies
    assert (await client.get("/api/v1/users/me")).status_code == 401

    wrong = await submit_code(client, body["challenge"], "000000")
    assert wrong.status_code == 401
    done = await submit_code(client, body["challenge"], current_code("ana@firm.be"))
    assert done.status_code == 200
    assert (await client.get("/api/v1/users/me")).json()["email"] == "ana@firm.be"


# AUTH-02 c2: enrolment yields 10 one-time recovery codes, shown once.
async def test_enrolment_gives_ten_one_time_recovery_codes(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    body = await start_login(client, "ana@firm.be")
    done = (await submit_code(client, body["challenge"], current_code("ana@firm.be"))).json()

    codes = done["recovery_codes"]
    assert len(codes) == 10
    assert len(set(codes)) == 10

    other = second_client(client)
    again = await start_login(other, "ana@firm.be")
    assert again["step"] == "code"
    assert "recovery_codes" not in again
    assert (await submit_code(other, again["challenge"], codes[0])).status_code == 200
    reused = await start_login(second_client(client), "ana@firm.be")
    assert (await submit_code(client, reused["challenge"], codes[0])).status_code == 401


# AUTH-01 c3: wrong email or wrong password give one message.
@pytest.mark.parametrize(("email", "password"), [("ana@firm.be", "Wrong123!"), ("nobody@firm.be", PASSWORD)])
async def test_wrong_email_or_password_is_one_message(client, seeded_db, clock, email, password):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    response = await client.post("/api/v1/auth/login", data={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


# AUTH-01 c4: a deactivated account with the right password is denied and the attempt logged.
async def test_deactivated_user_is_denied_and_logged(client, seeded_db, clock):
    gone = await make_user(seeded_db, "gone@firm.be", RoleName.ANALYST)
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    admin = second_client(client)
    csrf = await login(admin, "admin@firm.be")
    assert (await admin.delete(f"/api/v1/users/{gone['id']}", headers=csrf)).status_code == 200

    response = await client.post("/api/v1/auth/login", data={"email": "gone@firm.be", "password": PASSWORD})

    assert response.status_code == 401
    denied = await actions(seeded_db, "login.denied")
    assert [(e.user_id, e.new_values) for e in denied] == [(gone["id"], {"reason": "inactive"})]


# AUTH-01 c5: login is rate limited per account (lock) and per IP (crudauth lockout), and CSRF-protected.
async def test_login_is_rate_limited_per_ip_and_session_mutations_need_csrf(client, seeded_db, clock):
    for index in range(10):
        last = await client.post("/api/v1/auth/login", data={"email": f"x{index % 2}@firm.be", "password": "nope"})
    assert last.status_code == 429

    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    other = second_client(client, ip="10.0.0.9")
    await login(other, "ana@firm.be")
    assert (await other.post("/api/v1/auth/logout")).status_code == 403


# AUTH-01 c6: last login date, IP and device are stored and shown on the profile.
async def test_last_login_date_ip_and_device_show_on_profile(client, seeded_db, clock):
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    session = second_client(client, ip="81.82.83.84")
    await login(session, "ana@firm.be")

    profile = (await session.get(f"/api/v1/users/{ana['id']}/security")).json()

    assert datetime.fromisoformat(profile["last_login_at"]) == NOW
    assert profile["last_login_ip"] == "81.82.83.84"
    assert profile["last_login_device"] == "Safari on Mac OS X"


# AUTH-01 c7: a service error yields a clear message with no technical detail.
async def test_login_service_error_has_no_technical_details(client, seeded_db, clock, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("connection to server at 10.1.2.3 failed")

    monkeypatch.setattr(security_service.SecurityService, "state", boom)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    response = await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": PASSWORD})

    assert response.status_code == 500
    assert response.json()["detail"] == "Something went wrong. Please try again."
    assert "10.1.2.3" not in response.text


# AUTH-02 c3 / AUTH-06 c2: five wrong codes lock the account 15 minutes, and the admin is alerted.
async def test_five_wrong_codes_lock_for_fifteen_minutes_and_alert_admin(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(second_client(client), "ana@firm.be")

    body = await start_login(client, "ana@firm.be")
    statuses = [(await submit_code(client, body["challenge"], "000000")).status_code for _ in range(5)]
    assert statuses == [401, 401, 401, 401, 423]
    assert [m.subject for m in mailbox.to("admin@firm.be")] == ["Account locked"]

    sixth = await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": PASSWORD})
    assert sixth.status_code == 423
    clock.advance(timedelta(minutes=14))
    assert (await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": PASSWORD})).status_code == 423
    clock.advance(timedelta(minutes=2))
    assert (await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": PASSWORD})).status_code == 200


# AUTH-06 c2: failed and denied attempts count together; older than 15 minutes they drop out.
async def test_failed_and_denied_attempts_in_fifteen_minutes_lock(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await make_user(seeded_db, "nobody@firm.be", None)

    async def attempt(password: str) -> int:
        return (await client.post("/api/v1/auth/login", data={"email": "nobody@firm.be", "password": password})).status_code

    assert await attempt(PASSWORD) == 403
    clock.advance(timedelta(minutes=16))
    for _ in range(4):
        clock.advance(timedelta(minutes=1))
        assert await attempt(PASSWORD) == 403
    clock.advance(timedelta(minutes=1))
    assert await attempt("Wrong123!") == 423
    assert mailbox.to("admin@firm.be")
    assert await actions(seeded_db, "user.locked")


# AUTH-06 c3: admin unlock lets the user in immediately, and is audited.
async def test_admin_unlock_is_immediate_and_audited(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    for _ in range(5):
        await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": "Wrong123!"})
    assert (await client.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": PASSWORD})).status_code == 423

    admin = second_client(client, ip="10.9.9.9")
    csrf = await login(admin, "admin@firm.be")
    assert (await admin.post(f"/api/v1/users/{ana['id']}/unlock", headers=csrf)).status_code == 204

    await login(client, "ana@firm.be")
    unlocked = await actions(seeded_db, "user.unlocked")
    assert [(e.record_id, e.user_id is not None) for e in unlocked] == [(str(ana["id"]), True)]


# AUTH-02 c4: Trust this device skips the code for 30 days; the admin can turn it off.
async def test_trusted_device_skips_code_for_thirty_days_unless_admin_disables(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(client, "ana@firm.be", trust_device=True)

    clock.advance(timedelta(days=29))
    assert (await start_login(client, "ana@firm.be"))["step"] == "done"
    clock.advance(timedelta(days=2))
    assert (await start_login(client, "ana@firm.be"))["step"] == "code"

    await login(client, "ana@firm.be", trust_device=True)
    admin = second_client(client)
    csrf = await login(admin, "admin@firm.be")
    off = await admin.put("/api/v1/security/policy", json={"trusted_devices_enabled": False}, headers=csrf)
    assert off.json() == {"trusted_devices_enabled": False}
    assert (await start_login(client, "ana@firm.be"))["step"] == "code"


# AUTH-02 c5: admin resets 2FA, the user re-enrols at next login, the reset is audited.
async def test_admin_2fa_reset_forces_re_enrolment_and_is_audited(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(second_client(client), "ana@firm.be")
    old_secret = TOTP_SECRETS["ana@firm.be"]

    admin = second_client(client)
    csrf = await login(admin, "admin@firm.be")
    assert (await admin.post(f"/api/v1/users/{ana['id']}/reset-2fa", headers=csrf)).status_code == 204

    body = await start_login(client, "ana@firm.be")
    assert body["step"] == "enrol"
    assert (await submit_code(client, body["challenge"], totp_code(old_secret, NOW))).status_code == 401
    assert [e.record_id for e in await actions(seeded_db, "user.2fa_reset")] == [str(ana["id"])]


# AUTH-06 c1: a new country or device emails the user and the admin.
async def test_new_country_or_device_emails_user_and_admin(client, seeded_db, clock, mailbox, geo):
    geo.countries.update({"81.0.0.1": "BE", "81.0.0.2": "FR"})
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await login(second_client(client, ip="81.0.0.1"), "ana@firm.be")
    await login(second_client(client, ip="81.0.0.1"), "ana@firm.be")
    assert mailbox.to("ana@firm.be") == []

    await login(second_client(client, ip="81.0.0.2"), "ana@firm.be")
    assert len(mailbox.to("ana@firm.be")) == 1
    assert "new country: FR" in mailbox.to("ana@firm.be")[0].body
    assert len(mailbox.to("admin@firm.be")) == 1

    await login(second_client(client, OTHER_BROWSER, ip="81.0.0.2"), "ana@firm.be")
    assert "new device: Chrome on Windows" in mailbox.to("ana@firm.be")[1].body


# AUTH-06 c4 / AUTH-12: travelling outside the EU suppresses the alert during the range only.
async def test_travel_flag_silences_non_eu_alerts_and_ends_after_range(client, seeded_db, clock, mailbox, geo):
    geo.countries.update({"81.0.0.1": "BE", "8.8.8.8": "US", "1.1.1.1": "JP"})
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    home = second_client(client, ip="81.0.0.1")
    csrf = await login(home, "ana@firm.be")

    flagged = await home.put(
        f"/api/v1/users/{ana['id']}/travel",
        json={"travel_from": str(NOW.date()), "travel_until": str(NOW.date() + timedelta(days=3))},
        headers=csrf,
    )
    assert flagged.json()["travelling"] is True

    await login(second_client(client, ip="8.8.8.8"), "ana@firm.be")
    assert mailbox.to("ana@firm.be") == []

    clock.advance(timedelta(days=4))
    assert (await home.get(f"/api/v1/users/{ana['id']}/security")).json()["travelling"] is False
    await login(second_client(client, ip="1.1.1.1"), "ana@firm.be")
    assert len(mailbox.to("ana@firm.be")) == 1


# AUTH-12: an admin can set the range on another user's record; others cannot.
async def test_admin_sets_travel_on_a_user_record(client, seeded_db, clock):
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    ana = await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    bob = await make_user(seeded_db, "bob@firm.be", RoleName.ANALYST)
    admin = second_client(client)
    csrf = await login(admin, "admin@firm.be")
    span = {"travel_from": str(date(2030, 3, 1)), "travel_until": str(date(2030, 3, 10))}

    assert (await admin.put(f"/api/v1/users/{ana['id']}/travel", json=span, headers=csrf)).json()["travelling"] is True
    bob_csrf = await login(client, "bob@firm.be")
    assert (await client.put(f"/api/v1/users/{ana['id']}/travel", json=span, headers=bob_csrf)).status_code == 403
    assert bob["id"]
    assert await actions(seeded_db, "user.travel_changed")


# Step-up: a sensitive action can demand the code again.
async def test_step_up_requires_a_fresh_code(client, seeded_db, clock):
    router = APIRouter()

    @router.post("/__step-up-probe")
    async def probe(user: StepUpUserDep) -> dict:
        return {"id": user["id"]}

    app.include_router(router)
    try:
        await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
        csrf = await login(client, "ana@firm.be")
        missing = await client.post("/__step-up-probe", headers=csrf)
        assert missing.status_code == 401
        assert missing.headers["x-step-up"] == "required"
        ok = await client.post("/__step-up-probe", headers={**csrf, "X-Step-Up-Code": current_code("ana@firm.be")})
        assert ok.status_code == 200
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/__step-up-probe"]
