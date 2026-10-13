import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..clock import Clock
from ..logging import get_logger

logger = get_logger()

JobFunction = Callable[[AsyncSession, datetime], Awaitable[None]]


@dataclass
class Job:
    name: str
    interval: timedelta
    run: JobFunction
    last_run: datetime | None = field(default=None)

    def is_due(self, now: datetime) -> bool:
        return self.last_run is None or now - self.last_run >= self.interval


class JobRunner:
    """Runs registered jobs on an interval. Every job must be idempotent and take "now" only from
    the argument it is given, so the test hook and the clock can drive it deterministically."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._task: asyncio.Task[None] | None = None

    def register(self, name: str, interval: timedelta, run: JobFunction) -> None:
        self._jobs[name] = Job(name=name, interval=interval, run=run)

    def unregister(self, name: str) -> None:
        self._jobs.pop(name, None)

    @property
    def names(self) -> list[str]:
        return sorted(self._jobs)

    async def run_due(self, sessions: async_sessionmaker[AsyncSession], clock: Clock, *, force: bool = False) -> list[str]:
        now = clock.now()
        ran: list[str] = []
        for job in list(self._jobs.values()):
            if not force and not job.is_due(now):
                continue
            async with sessions() as db:
                try:
                    await job.run(db, now)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception(f"Scheduled job {job.name} failed")
                    continue
            job.last_run = now
            ran.append(job.name)
        return ran

    def start(self, sessions: async_sessionmaker[AsyncSession], clock: Clock, tick: timedelta) -> None:
        async def loop() -> None:
            while True:
                await self.run_due(sessions, clock)
                await asyncio.sleep(tick.total_seconds())

        self._task = asyncio.create_task(loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None


job_runner = JobRunner()
