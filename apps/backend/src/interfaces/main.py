from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from ..infrastructure.app_factory import create_application, lifespan_factory
from ..infrastructure.clock import get_clock
from ..infrastructure.config.settings import get_settings
from ..infrastructure.database import session as database_session
from ..infrastructure.jobs import job_runner
from ..infrastructure.security import validate_production_security
from ..interfaces.api import router
from ..modules.role.authorization import require_permission
from ..modules.role.permissions import Permission
from ..modules.role.service import seed_default_roles

settings = get_settings()


@asynccontextmanager
async def lifespan_with_security(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.PRODUCTION_SECURITY_VALIDATION_ENABLED:
        validate_production_security(settings)

    default_lifespan = lifespan_factory(settings, create_tables_on_startup=settings.CREATE_TABLES_ON_STARTUP)

    async with default_lifespan(app):
        # Read off the module at call time so tests can point startup at their own database.
        sessions = database_session.local_session
        async with sessions() as db:
            await seed_default_roles(db)
        if settings.SCHEDULED_JOBS_ENABLED:
            job_runner.start(sessions, get_clock(), timedelta(seconds=settings.SCHEDULED_JOBS_TICK_SECONDS))
        try:
            yield
        finally:
            await job_runner.stop()


app = create_application(
    router=router,
    settings=settings,
    lifespan=lifespan_with_security,
    create_tables_on_startup=None,
    enable_cors=None,
    cors_origins=None,
    enable_docs_in_production=None,
    docs_production_dependency=require_permission(Permission.SETTINGS_MANAGE).dependency,
    enable_gzip=None,
    openapi_prefix=None,
    title="M&A CRM",
    summary="M&A CRM API",
    description="M&A CRM: email login, one role per user, permission matrix, append-only audit log.",
    version="0.19.0",
    contact={
        "name": "Benav Labs",
        "url": "https://github.com/benavlabs/FastAPI-boilerplate",
        "email": "contact@benav.io",
    },
    license_info={
        "name": "MIT",
        "identifier": "MIT",
    },
    openapi_tags=None,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
