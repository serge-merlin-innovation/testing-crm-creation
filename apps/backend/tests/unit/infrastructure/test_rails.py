from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.infrastructure.clock import FrozenClock
from src.infrastructure.i18n import SUPPORTED_LANGUAGES, format_date, format_datetime, format_number, translate
from src.infrastructure.i18n.catalogue import catalogue
from src.infrastructure.jobs import JobRunner


@pytest.mark.parametrize(
    ("language", "expected"), [("en", "Invalid email or password"), ("fr", "Adresse e-mail ou mot de passe invalide")]
)
def test_translate_picks_the_language(language, expected):
    assert translate("auth.invalid_credentials", language) == expected


def test_translate_falls_back_to_english():
    assert translate("auth.invalid_credentials", "de") == "Invalid email or password"


def test_every_catalogue_has_the_same_keys():
    keys = [set(catalogue(language)) for language in SUPPORTED_LANGUAGES]
    assert all(key_set == keys[0] for key_set in keys)


def test_belgian_date_format():
    assert format_date(date(2026, 3, 7)) == "07/03/2026"
    assert format_datetime(datetime(2026, 7, 1, 10, 0, tzinfo=UTC)) == "01/07/2026 12:00"


@pytest.mark.parametrize(("language", "expected"), [("fr", "1.234,56"), ("nl", "1.234,56"), ("en", "1,234.56")])
def test_belgian_number_format(language, expected):
    assert format_number(1234.56, language) == expected


async def test_job_runner_only_runs_due_jobs():
    clock = FrozenClock(datetime(2030, 1, 1, tzinfo=UTC))
    ran: list[datetime] = []

    async def job(db, now):
        ran.append(now)

    session = MagicMock()
    session.__aenter__ = _async_return(MagicMock(commit=_async_return(None)))
    session.__aexit__ = _async_return(None)
    runner = JobRunner()
    runner.register("daily", timedelta(days=1), job)

    await runner.run_due(lambda: session, clock)
    await runner.run_due(lambda: session, clock)
    clock.advance(timedelta(days=1))
    await runner.run_due(lambda: session, clock)

    assert ran == [datetime(2030, 1, 1, tzinfo=UTC), datetime(2030, 1, 2, tzinfo=UTC)]


def _async_return(value):
    async def call(*_args, **_kwargs):
        return value

    return call
