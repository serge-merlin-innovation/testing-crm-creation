import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import async_session

pytestmark = pytest.mark.asyncio


class TestDatabaseSession:
    async def test_async_session(self):
        async for session in async_session():
            assert isinstance(session, AsyncSession)
            break  # Just test that we can get a session

    async def test_session_transaction(self, db_session: AsyncSession):
        result = await db_session.execute(text("SELECT 1 as test_value"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1

    async def test_session_rollback(self, db_session: AsyncSession):
        await db_session.begin()

        await db_session.execute(text("SELECT 1"))

        await db_session.rollback()

        result = await db_session.execute(text("SELECT 2"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 2

    async def test_session_commit(self, db_session: AsyncSession):
        result = await db_session.execute(text("SELECT 3"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 3

        await db_session.commit()
