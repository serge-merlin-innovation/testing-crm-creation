from crudauth import get_password_hash
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.role.models import Role
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


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", data={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}
