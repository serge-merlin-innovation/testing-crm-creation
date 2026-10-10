from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..infrastructure.app_factory import create_application, lifespan_factory
from ..infrastructure.auth.dependencies import set_bearer_resolver
from ..infrastructure.breach import StaticBreachList, set_breach_checker
from ..infrastructure.clock import get_clock
from ..infrastructure.config.settings import get_settings
from ..infrastructure.database import session as database_session
from ..infrastructure.dependencies import AsyncSessionDep
from ..infrastructure.geoip import get_geoip
from ..infrastructure.i18n.middleware import LocalizeErrorsMiddleware
from ..infrastructure.jobs import job_runner
from ..infrastructure.security import validate_production_security
from ..infrastructure.security.production_validator import validate_geoip
from ..interfaces.api import router
from ..interfaces.api.openapi import build_openapi
from ..interfaces.api.versions import version_for
from ..modules.access.jobs import register_jobs as register_access_jobs
from ..modules.api_access.dependencies import resolve_bearer
from ..modules.audit.scope import set_audit_scope
from ..modules.buyer.jobs import register_jobs as register_buyer_jobs
from ..modules.compliance.jobs import register_jobs as register_compliance_jobs
from ..modules.compliance.service import install as install_compliance
from ..modules.data_import.jobs import register_jobs as register_import_jobs
from ..modules.fee.service import on_closed_won as raise_invoice_task
from ..modules.mandate.jobs import register_jobs as register_deal_jobs
from ..modules.mandate.pipeline import on_closed_won
from ..modules.mandate.policy import visible_deal_ids
from ..modules.notification.visibility import set_visible_deals
from ..modules.operations.jobs import register_jobs as register_operations_jobs
from ..modules.origination.audit_scope import readable_rows as deal_wall_audit_scope
from ..modules.origination.jobs import register_jobs as register_origination_jobs
from ..modules.picklist.service import seed_default_picklists
from ..modules.privacy.jobs import register_jobs as register_privacy_jobs
from ..modules.role.authorization import require_permission
from ..modules.role.permissions import Permission
from ..modules.role.service import seed_default_roles
from ..modules.task.jobs import register_jobs as register_task_jobs

settings = get_settings()
register_task_jobs()
register_import_jobs()
register_privacy_jobs()
register_deal_jobs()
on_closed_won(raise_invoice_task)
register_compliance_jobs()
register_access_jobs()
register_buyer_jobs()
install_compliance()
register_origination_jobs()
register_operations_jobs()
set_audit_scope(deal_wall_audit_scope)
set_visible_deals(visible_deal_ids)
set_bearer_resolver(resolve_bearer)
if not settings.BREACH_CHECK_ENABLED:
    set_breach_checker(StaticBreachList(set()))


@asynccontextmanager
async def lifespan_with_security(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.PRODUCTION_SECURITY_VALIDATION_ENABLED:
        validate_production_security(settings)
        validate_geoip(settings, get_geoip())

    default_lifespan = lifespan_factory(settings, create_tables_on_startup=settings.CREATE_TABLES_ON_STARTUP)

    async with default_lifespan(app):
        # Read off the module at call time so tests can point startup at their own database.
        sessions = database_session.local_session
        async with sessions() as db:
            await seed_default_roles(db)
            await seed_default_picklists(db)
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


@app.get("/health/ready", tags=["System"], responses={503: {"description": "The database does not answer"}})
async def readiness_check(db: AsyncSessionDep) -> JSONResponse:
    """What the uptime probe calls (NFR-03): the app answers AND its database does."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ready", "database": "ok"})


app.add_middleware(LocalizeErrorsMiddleware)
app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]


@app.middleware("http")
async def announce_deprecation(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    version = version_for(request.url.path)
    if version is not None and version.sunset is not None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = version.sunset.isoformat()
    return response
