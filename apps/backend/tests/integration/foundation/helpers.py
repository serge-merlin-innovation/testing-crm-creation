from urllib.parse import parse_qs, urlparse

from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.clock import get_clock
from src.modules.role.models import Role
from src.modules.security.totp import totp_code
from src.modules.user.models import User

PASSWORD = "Password123!"


async def role_id(db: AsyncSession, name: str) -> int:
    return (await db.execute(select(Role.id).where(Role.name == name))).scalar_one()


async def make_user(db: AsyncSession, email: str, role_name: str | None) -> dict:
    user = User(
        name=email.split("@")[0][:30],
        email=email,
        hashed_password=get_password_hash(PASSWORD),
        role_id=await role_id(db, role_name) if role_name else None,
    )
    db.add(user)
    await db.commit()
    return {"id": user.id, "email": email, "password": PASSWORD}


# TOTP secrets captured at enrolment, by email, so later logins in the same test can answer the code.
TOTP_SECRETS: dict[str, str] = {}


def secret_from_uri(uri: str) -> str:
    return parse_qs(urlparse(uri).query)["secret"][0]


def current_code(email: str) -> str:
    return totp_code(TOTP_SECRETS[email.lower()], get_clock().now())


async def start_login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict:
    response = await client.post("/api/v1/auth/login", data={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    if body["step"] == "enrol":
        TOTP_SECRETS[email.lower()] = secret_from_uri(body["otpauth_uri"])
    return body


async def login(client: AsyncClient, email: str, password: str = PASSWORD, trust_device: bool = False) -> dict[str, str]:
    """Password, then enrolment or the TOTP code: the whole two-step login."""
    body = await start_login(client, email, password)
    if body["step"] != "done":
        response = await client.post(
            "/api/v1/auth/login/second-factor",
            json={"challenge": body["challenge"], "code": current_code(email), "trust_device": trust_device},
        )
        assert response.status_code == 200, response.text
        body = response.json()
    return {"X-CSRF-Token": body["csrf_token"]}
