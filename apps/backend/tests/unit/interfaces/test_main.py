from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from fastapi import FastAPI

from src.interfaces import main


async def test_custom_lifespan_preserves_create_tables_setting(monkeypatch) -> None:
    app = MagicMock(spec=FastAPI)

    @asynccontextmanager
    async def wrapped_lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        yield

    monkeypatch.setattr(main.settings, "CREATE_TABLES_ON_STARTUP", False)
    with (
        patch.object(main, "validate_production_security"),
        patch.object(main, "lifespan_factory", return_value=wrapped_lifespan) as factory,
        patch.object(main, "seed_default_roles"),
        patch.object(main, "seed_default_picklists"),
    ):
        async with main.lifespan_with_security(app):
            pass

    factory.assert_called_once_with(main.settings, create_tables_on_startup=False)
