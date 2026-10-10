from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.clock import SystemClock, set_clock
from src.infrastructure.email import EmailMessage, LoggingEmailSender, get_email_sender, set_email_sender
from src.infrastructure.jobs import job_runner
from src.modules.audit.models import AuditEntry
from src.modules.role.permissions import RoleName

from .helpers import login, make_user

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def restore_clock():
    yield
    set_clock(SystemClock())


async def test_frozen_clock_drives_audit_timestamps(client: AsyncClient, seeded_db: AsyncSession):
    frozen = datetime(2030, 3, 1, 9, 30, tzinfo=UTC)
    await client.put("/api/v1/test-hooks/clock", json={"now": frozen.isoformat()})
    await make_user(seeded_db, "admin@firm.be", RoleName.ADMIN)
    await login(client, "admin@firm.be")

    entry = (await seeded_db.execute(select(AuditEntry).where(AuditEntry.action == "login"))).scalar_one()

    assert entry.created_at == frozen
    assert entry.retain_until == frozen.replace(year=2040)


async def test_run_jobs_now_runs_every_job_with_the_injected_clock(
    client: AsyncClient, seeded_db: AsyncSession, startup_against_test_db
):
    seen: list[datetime] = []

    async def job(db: AsyncSession, now: datetime) -> None:
        seen.append(now)

    job_runner.register("probe", timedelta(days=1), job)
    try:
        frozen = datetime(2031, 1, 1, tzinfo=UTC)
        await client.put("/api/v1/test-hooks/clock", json={"now": frozen.isoformat()})
        first = await client.post("/api/v1/test-hooks/jobs/run")
        second = await client.post("/api/v1/test-hooks/jobs/run")
    finally:
        job_runner.unregister("probe")

    assert "probe" in first.json()["ran"]
    assert "probe" in second.json()["ran"]
    assert seen == [frozen, frozen]


async def test_captured_email_can_be_read_back(client: AsyncClient):
    try:
        assert (await client.post("/api/v1/test-hooks/emails/capture")).json() == {"capturing": True}
        await get_email_sender().send(EmailMessage(to="ann@firm.be", subject="Hi", body="link"))
        await get_email_sender().send(EmailMessage(to="bob@firm.be", subject="Other", body="x"))

        sent = (await client.get("/api/v1/test-hooks/emails", params={"to": "ann@firm.be"})).json()
    finally:
        set_email_sender(LoggingEmailSender())

    assert sent == [{"to": "ann@firm.be", "subject": "Hi", "body": "link"}]
