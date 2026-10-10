from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from ..clock import FrozenClock, SystemClock, get_clock, set_clock
from ..database import session as database_session
from ..email import InMemoryEmailSender, get_email_sender, set_email_sender
from ..jobs import job_runner

# Mounted only outside production and staging (see interfaces/api/v1). Lets tests drive time and
# the scheduler deterministically.
router = APIRouter(tags=["Test hooks"])


class ClockSet(BaseModel):
    now: datetime | None = None


@router.put("/clock", summary="Freeze the clock at a time, or unfreeze it with null")
async def set_test_clock(values: ClockSet) -> dict[str, str]:
    set_clock(FrozenClock(values.now) if values.now else SystemClock())
    return {"now": get_clock().now().isoformat()}


class SentEmail(BaseModel):
    to: str
    subject: str
    body: str


@router.post("/emails/capture", summary="Keep outgoing email in memory so a test can read it")
async def capture_emails() -> dict[str, bool]:
    if not isinstance(get_email_sender(), InMemoryEmailSender):
        set_email_sender(InMemoryEmailSender())
    return {"capturing": True}


@router.get("/emails", summary="Captured email sent to an address, oldest first")
async def read_emails(to: str) -> list[SentEmail]:
    sender = get_email_sender()
    if not isinstance(sender, InMemoryEmailSender):
        return []
    return [SentEmail(to=m.to, subject=m.subject, body=m.body) for m in sender.to(to)]


@router.post("/jobs/run", summary="Run every scheduled job now")
async def run_jobs_now() -> dict[str, list[str]]:
    return {"ran": await job_runner.run_due(database_session.local_session, get_clock(), force=True)}
