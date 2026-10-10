import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_DIRECTORY = Path(__file__).parents[3]

pytestmark = pytest.mark.asyncio


def alembic(database_url: str, *arguments: str) -> None:
    environment = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


async def test_migration_promotes_superusers_and_makes_the_audit_log_append_only(test_db_url):
    admin_url = test_db_url
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.execute(text("DROP DATABASE IF EXISTS migration_check"))
        await connection.execute(text("CREATE DATABASE migration_check"))
    await engine.dispose()
    url = admin_url.rsplit("/", 1)[0] + "/migration_check"

    alembic(url, "upgrade", "a90213be73b8")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                'INSERT INTO "user" (name, username, email, hashed_password, profile_image_url, is_superuser, '
                "email_verified, created_at, is_deleted) VALUES ('Boss', 'boss', 'boss@firm.be', 'x', 'x', true, "
                "false, now(), false)"
            )
        )
    await engine.dispose()

    alembic(url, "upgrade", "head")

    engine = create_async_engine(url)
    async with engine.begin() as connection:
        role = (
            await connection.execute(
                text("SELECT r.name FROM \"user\" u JOIN roles r ON r.id = u.role_id WHERE u.email = 'boss@firm.be'")
            )
        ).scalar_one()
        columns = set(
            (
                await connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"))
            ).scalars()
        )
        await connection.execute(
            text("INSERT INTO audit_log (action, created_at, retain_until) VALUES ('login', now(), now())")
        )
    for statement in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError, match="append-only|permission denied"):
                await connection.execute(text(statement))
    await engine.dispose()

    assert role == "Admin"
    assert not columns & {"username", "is_superuser", "microsoft_id", "oauth_provider"}
