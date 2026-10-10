import csv
import io
import re
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.breach import HibpRangeChecker, StaticBreachList, set_breach_checker
from src.infrastructure.clock import FrozenClock, SystemClock, set_clock
from src.infrastructure.email import InMemoryEmailSender, LoggingEmailSender, set_email_sender
from src.interfaces.main import app
from src.modules.role.permissions import RoleName
from src.modules.security.models import UserSecurity
from src.modules.user.models import User
from tests.integration.foundation.helpers import (
    PASSWORD,
    TOTP_SECRETS,
    current_code,
    login,
    make_user,
    role_id,
    secret_from_uri,
)

pytestmark = pytest.mark.asyncio

NOW = datetime(2030, 3, 4, 9, 0, tzinfo=UTC)
STRONG = "violet-harbour-lantern-42"
OTHER_STRONG = "copper-meadow-orbit-77"
BREACHED = "correcthorsebattery"


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


@pytest.fixture(autouse=True)
def breaches():
    fake = StaticBreachList({BREACHED})
    set_breach_checker(fake)
    yield fake
    set_breach_checker(StaticBreachList(set()))


def fresh_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def link_token(body: str, path: str) -> str:
    match = re.search(rf"{path}\?token=([\w-]+)", body)
    assert match, body
    return match.group(1)


async def admin(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    await make_user(db, "admin@firm.be", RoleName.ADMIN)
    return await login(client, "admin@firm.be")


async def invite(client: AsyncClient, csrf: dict[str, str], db: AsyncSession, email: str = "nina@firm.be"):
    return await client.post(
        "/api/v1/users/",
        json={
            "first_name": "Nina",
            "last_name": "Claes",
            "email": email,
            "title": "Associate",
            "role_id": await role_id(db, RoleName.ANALYST),
        },
        headers=csrf,
    )


def invitation_token(mailbox: InMemoryEmailSender, email: str) -> str:
    message = next(m for m in reversed(mailbox.to(email)) if m.subject == "You are invited to the CRM")
    return link_token(message.body, "/accept-invitation")


async def accept(client: AsyncClient, token: str, password: str = STRONG):
    return await client.post("/api/v1/auth/invitations/accept", json={"token": token, "password": password})


async def activate(client: AsyncClient, csrf, db, mailbox, email: str = "nina@firm.be") -> None:
    assert (await invite(client, csrf, db, email)).status_code == 201
    async with fresh_client() as invitee:
        body = (await accept(invitee, invitation_token(mailbox, email))).json()
        TOTP_SECRETS[email] = secret_from_uri(body["otpauth_uri"])
        done = await invitee.post(
            "/api/v1/auth/login/second-factor", json={"challenge": body["challenge"], "code": current_code(email)}
        )
        assert done.status_code == 200, done.text


async def user_row(db: AsyncSession, email: str) -> User:
    db.expire_all()
    return (await db.execute(select(User).where(User.email == email))).scalar_one()


# ADM-01 c1 + AUTH-08: created as Invited and an invitation email is sent.
async def test_admin_creates_an_invited_user_and_an_invitation_is_sent(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)

    response = await invite(client, csrf, seeded_db)

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "invited"
    assert response.json()["title"] == "Associate"
    assert response.json()["name"] == "Nina Claes"
    subjects = [m.subject for m in mailbox.to("nina@firm.be")]
    assert "You are invited to the CRM" in subjects
    assert invitation_token(mailbox, "nina@firm.be")


async def test_invited_user_cannot_log_in_before_accepting(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)

    async with fresh_client() as other:
        response = await other.post("/api/v1/auth/login", data={"email": "nina@firm.be", "password": ""})

    assert response.status_code in (401, 422)


# ADM-01 c5: welcome email with the CRM link and the role.
async def test_new_user_gets_a_welcome_email_with_link_and_role(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)

    welcome = next(m for m in mailbox.to("nina@firm.be") if m.subject == "Welcome to the CRM")

    assert "http://localhost:3000" in welcome.body
    assert RoleName.ANALYST.value in welcome.body


# ADM-01 c3
async def test_creating_an_existing_email_says_the_user_exists(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)

    again = await invite(client, csrf, seeded_db, "NINA@firm.be")

    assert again.status_code == 409
    assert again.json()["detail"] == "A user with this email already exists."


# ADM-01 c2: after 72h without acceptance the list offers resend, and resend issues a fresh link.
async def test_unaccepted_invitation_can_be_resent_after_72_hours(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    nina = (await invite(client, csrf, seeded_db)).json()
    old_token = invitation_token(mailbox, "nina@firm.be")

    listed = (await client.get("/api/v1/users/", params={"status": "invited"})).json()["data"]
    assert listed[0]["can_resend_invitation"] is False

    clock.advance(timedelta(hours=73))
    listed = (await client.get("/api/v1/users/", params={"status": "invited"})).json()["data"]
    assert listed[0]["can_resend_invitation"] is True

    resent = await client.post(f"/api/v1/users/{nina['id']}/invitation", headers=csrf)
    assert resent.status_code == 204
    new_token = invitation_token(mailbox, "nina@firm.be")
    assert new_token != old_token
    async with fresh_client() as invitee:
        assert (await accept(invitee, new_token)).status_code == 200


# ADM-01 c4: each CSV row validated, invitations sent in bulk.
async def test_csv_import_validates_each_row_and_invites_in_bulk(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    rows = (
        "first_name,last_name,email,title,role\n"
        "Jan,Peeters,jan@firm.be,Partner,Partner\n"
        "Eva,Maes,eva@firm.be,Analyst,Analyst\n"
        "Bad,Email,not-an-email,Analyst,Analyst\n"
        "No,Role,norole@firm.be,Analyst,Wizard\n"
        "Dup,Admin,admin@firm.be,Analyst,Analyst\n"
    )

    response = await client.post("/api/v1/users/import", files={"file": ("users.csv", rows, "text/csv")}, headers=csrf)

    assert response.status_code == 200, response.text
    results = response.json()["rows"]
    assert [r["status"] for r in results] == ["created", "created", "error", "error", "error"]
    assert results[2]["field"] == "email"
    assert results[3]["field"] == "role"
    assert "exists" in results[4]["message"]
    assert invitation_token(mailbox, "jan@firm.be")
    assert invitation_token(mailbox, "eva@firm.be")
    assert mailbox.to("norole@firm.be") == []


# AUTH-08 c1: the link sets a password and enrols 2FA.
async def test_invitation_link_sets_password_and_enrols_two_factor(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)
    token = invitation_token(mailbox, "nina@firm.be")

    async with fresh_client() as invitee:
        assert (await invitee.get("/api/v1/auth/invitations", params={"token": token})).json() == {
            "email": "nina@firm.be",
            "first_name": "Nina",
            "last_name": "Claes",
        }
        body = (await accept(invitee, token)).json()
        assert body["step"] == "enrol"
        assert body["otpauth_uri"].startswith("otpauth://totp/")
        TOTP_SECRETS["nina@firm.be"] = secret_from_uri(body["otpauth_uri"])
        done = await invitee.post(
            "/api/v1/auth/login/second-factor", json={"challenge": body["challenge"], "code": current_code("nina@firm.be")}
        )
        assert done.status_code == 200
        me = (await invitee.get("/api/v1/users/me")).json()

    assert me["status"] == "active"
    state = await seeded_db.get(UserSecurity, me["id"])
    assert state is not None
    assert state.totp_enabled
    async with fresh_client() as again:
        assert (await login(again, "nina@firm.be", STRONG))["X-CSRF-Token"]


# AUTH-08 c2: older than 72h or already used is refused, with a hint to ask the admin.
async def test_expired_or_used_invitation_is_refused(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)
    await invite(client, csrf, seeded_db, "late@firm.be")
    used = invitation_token(mailbox, "nina@firm.be")
    late = invitation_token(mailbox, "late@firm.be")

    async with fresh_client() as invitee:
        assert (await accept(invitee, used)).status_code == 200
        reuse = await accept(invitee, used, OTHER_STRONG)
        clock.advance(timedelta(hours=72, seconds=1))
        expired = await accept(invitee, late)

    for refused in (reuse, expired):
        assert refused.status_code == 410
        assert "ask your administrator to resend" in refused.json()["detail"].lower()


# AUTH-08 c3: only a salted bcrypt/Argon2id hash is stored.
async def test_only_a_salted_hash_is_stored(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await activate(client, csrf, seeded_db, mailbox)

    stored = (await user_row(seeded_db, "nina@firm.be")).hashed_password

    assert STRONG not in stored
    assert stored.startswith("$2b$") or stored.startswith("$argon2id$")


# AUTH-09 c1
async def test_short_password_is_rejected_with_the_rule(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)

    async with fresh_client() as invitee:
        response = await accept(invitee, invitation_token(mailbox, "nina@firm.be"), "Short-pass1")

    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "password", "message": "Use at least 12 characters."}]


# AUTH-09 c2
@pytest.mark.parametrize(
    ("password", "message"),
    [
        (BREACHED, "This password appears in a known data breach. Choose another."),
        ("my-name-is-nina-ok", "The password must not contain your name or email."),
        ("Claes-forever-2030", "The password must not contain your name or email."),
        ("nina@firm.be-secret", "The password must not contain your name or email."),
    ],
)
async def test_breached_or_personal_password_is_rejected(client, seeded_db, clock, mailbox, password, message):
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)

    async with fresh_client() as invitee:
        response = await accept(invitee, invitation_token(mailbox, "nina@firm.be"), password)

    assert response.status_code == 422
    assert response.json()["errors"][0]["message"] == message


async def test_hibp_checker_sends_only_the_hash_prefix():
    seen: list[str] = []

    async def fake_get(url: str) -> str:
        seen.append(url)
        # SHA-1("password") = 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
        return "1E4C9B93F3F0682250B6CF8331B7EE68FD8:3861493\r\nFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:1"

    checker = HibpRangeChecker(fetch=fake_get)

    assert await checker.is_breached("password") is True
    assert seen == ["https://api.pwnedpasswords.com/range/5BAA6"]
    assert await checker.is_breached("violet-harbour-lantern-42") is False


# AUTH-09 c3
async def test_reusing_one_of_the_last_five_passwords_is_rejected(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await activate(client, csrf, seeded_db, mailbox)
    async with fresh_client() as nina:
        nina_csrf = await login(nina, "nina@firm.be", STRONG)
        history = [STRONG] + [f"rotating-secret-{n}-xyz" for n in range(5)]
        for previous, new in zip(history, history[1:], strict=False):
            clock.advance(timedelta(minutes=1))
            changed = await change_password(nina, nina_csrf, previous, new)
            assert changed.status_code == 204, changed.text

        clock.advance(timedelta(minutes=1))
        reused = await change_password(nina, nina_csrf, history[-1], history[2])
        clock.advance(timedelta(minutes=1))
        old_enough = await change_password(nina, nina_csrf, history[-1], history[0])

    assert reused.status_code == 422
    assert reused.json()["errors"][0]["message"] == "You used this password recently. Choose another."
    assert old_enough.status_code == 204


# AUTH-09 c4: a stricter policy applies at the next change, without forcing anyone out.
async def test_policy_change_applies_at_next_password_change_only(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await activate(client, csrf, seeded_db, mailbox)

    policy = await client.put("/api/v1/security/password-policy", json={"min_length": 30}, headers=csrf)
    assert policy.status_code == 200
    assert (await client.get("/api/v1/security/password-policy")).json() == {"min_length": 30, "history_count": 5}
    assert (await client.put("/api/v1/security/password-policy", json={"min_length": 8}, headers=csrf)).status_code == 422

    async with fresh_client() as nina:
        nina_csrf = await login(nina, "nina@firm.be", STRONG)
        clock.advance(timedelta(minutes=1))
        too_short = await change_password(nina, nina_csrf, STRONG, OTHER_STRONG)
        clock.advance(timedelta(minutes=1))
        long_enough = await change_password(nina, nina_csrf, STRONG, "a-much-longer-passphrase-for-thirty")

    assert too_short.status_code == 422
    assert too_short.json()["errors"][0]["message"] == "Use at least 30 characters."
    assert long_enough.status_code == 204


async def forgot(client: AsyncClient, email: str):
    return await client.post("/api/v1/auth/password/forgot", json={"email": email})


def reset_token(mailbox: InMemoryEmailSender, email: str) -> str:
    message = next(m for m in reversed(mailbox.to(email)) if m.subject == "Reset your CRM password")
    return link_token(message.body, "/reset-password")


# AUTH-10 c1
async def test_forgot_password_shows_the_same_message_whatever_the_email(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    known = await forgot(client, "ana@firm.be")
    unknown = await forgot(client, "ghost@firm.be")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mailbox.to("ana@firm.be")) == 1
    assert mailbox.to("ghost@firm.be") == []


# AUTH-10 c2
async def test_reset_link_is_single_use_and_expires_after_30_minutes(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await forgot(client, "ana@firm.be")
    superseded = reset_token(mailbox, "ana@firm.be")
    await forgot(client, "ana@firm.be")
    first = reset_token(mailbox, "ana@firm.be")

    older = await client.post("/api/v1/auth/password/reset", json={"token": superseded, "password": STRONG})
    used = await client.post("/api/v1/auth/password/reset", json={"token": first, "password": STRONG})
    reused = await client.post("/api/v1/auth/password/reset", json={"token": first, "password": OTHER_STRONG})
    await forgot(client, "ana@firm.be")
    late = reset_token(mailbox, "ana@firm.be")
    clock.advance(timedelta(minutes=30, seconds=1))
    expired = await client.post("/api/v1/auth/password/reset", json={"token": late, "password": OTHER_STRONG})

    assert older.status_code == 410
    assert used.status_code == 204
    assert reused.status_code == 410
    assert expired.status_code == 410
    assert "ask for a new one" in expired.json()["detail"].lower()


# AUTH-10 c3: other sessions end, 2FA is still required, a confirmation is sent.
async def test_reset_ends_sessions_keeps_two_factor_and_confirms(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    async with fresh_client() as laptop:
        await login(laptop, "ana@firm.be", trust_device=True)
        assert (await laptop.get("/api/v1/users/me")).status_code == 200

        async with fresh_client() as anonymous:
            await forgot(anonymous, "ana@firm.be")
            reset = await anonymous.post(
                "/api/v1/auth/password/reset", json={"token": reset_token(mailbox, "ana@firm.be"), "password": STRONG}
            )
            assert reset.status_code == 204
            assert "session_id" not in anonymous.cookies

        assert (await laptop.get("/api/v1/users/me")).status_code == 401
        relogin = await laptop.post("/api/v1/auth/login", data={"email": "ana@firm.be", "password": STRONG})

    assert relogin.json()["step"] == "code"
    assert "Your CRM password was changed" in [m.subject for m in mailbox.to("ana@firm.be")]


# AUTH-10 c4
async def test_fourth_reset_request_in_an_hour_is_refused(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)

    statuses = [(await forgot(client, "ana@firm.be")).status_code for _ in range(3)]
    fourth = await forgot(client, "ana@firm.be")
    ghost = [(await forgot(client, "ghost@firm.be")).status_code for _ in range(4)]
    clock.advance(timedelta(hours=1, seconds=1))
    later = await forgot(client, "ana@firm.be")

    assert statuses == [202, 202, 202]
    assert fourth.status_code == 429
    assert ghost[-1] == 429
    assert len(mailbox.to("ana@firm.be")) == 4
    assert later.status_code == 202


async def change_password(client: AsyncClient, csrf, current: str, new: str, code: str | None = None):
    email = (await client.get("/api/v1/users/me")).json()["email"]
    return await client.post(
        "/api/v1/users/me/password",
        json={"current_password": current, "new_password": new},
        headers={**csrf, "X-Step-Up-Code": code or current_code(email)},
    )


# AUTH-11
async def test_change_password_needs_current_password_and_code_and_ends_other_sessions(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    csrf = await login(client, "ana@firm.be")
    async with fresh_client() as phone:
        await login(phone, "ana@firm.be")

        wrong_current = await change_password(client, csrf, "not-my-password", STRONG)
        no_code = await client.post(
            "/api/v1/users/me/password", json={"current_password": PASSWORD, "new_password": STRONG}, headers=csrf
        )
        weak = await change_password(client, csrf, PASSWORD, "short")
        changed = await change_password(client, csrf, PASSWORD, STRONG)

        assert (await phone.get("/api/v1/users/me")).status_code == 401
    assert wrong_current.status_code == 422
    assert wrong_current.json()["errors"][0]["field"] == "current_password"
    assert no_code.status_code == 401
    assert weak.status_code == 422
    assert changed.status_code == 204
    assert (await client.get("/api/v1/users/me")).status_code == 200


# ADM-04 c1: filter by role or status, export to CSV.
async def test_admin_filters_users_by_role_and_status_and_exports_csv(client, seeded_db, clock, mailbox):
    csrf = await admin(client, seeded_db)
    await make_user(seeded_db, "ana@firm.be", RoleName.ANALYST)
    await make_user(seeded_db, "pat@firm.be", RoleName.PARTNER)
    await invite(client, csrf, seeded_db)
    analyst = await role_id(seeded_db, RoleName.ANALYST)

    by_role = (await client.get("/api/v1/users/", params={"role_id": analyst})).json()["data"]
    invited = (await client.get("/api/v1/users/", params={"status": "invited"})).json()["data"]
    active_analysts = (await client.get("/api/v1/users/", params={"role_id": analyst, "status": "active"})).json()["data"]
    export = await client.get("/api/v1/users/export", params={"role_id": analyst})

    assert sorted(u["email"] for u in by_role) == ["ana@firm.be", "nina@firm.be"]
    assert [u["email"] for u in invited] == ["nina@firm.be"]
    assert [u["email"] for u in active_analysts] == ["ana@firm.be"]
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert sorted(r["email"] for r in rows) == ["ana@firm.be", "nina@firm.be"]
    assert set(rows[0]) >= {"first_name", "last_name", "email", "title", "role", "status", "last_login_at", "dormant"}


# ADM-04 c2
async def test_user_without_login_for_90_days_is_flagged_dormant(client, seeded_db, clock, mailbox):
    await make_user(seeded_db, "old@firm.be", RoleName.ANALYST)
    async with fresh_client() as old:
        await login(old, "old@firm.be")
    clock.advance(timedelta(days=91))
    csrf = await admin(client, seeded_db)
    await invite(client, csrf, seeded_db)

    users = {u["email"]: u for u in (await client.get("/api/v1/users/", params={"items_per_page": 50})).json()["data"]}

    assert users["old@firm.be"]["dormant"] is True
    assert users["old@firm.be"]["last_login_at"].startswith("2030-03-04")
    assert users["admin@firm.be"]["dormant"] is False
    assert users["nina@firm.be"]["dormant"] is False
