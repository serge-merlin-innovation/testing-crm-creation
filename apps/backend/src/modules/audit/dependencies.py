from typing import Annotated

from fastapi import Depends, Request

from ...infrastructure.auth.dependencies import get_optional_user
from ...infrastructure.clock import Clock, get_clock
from .service import AuditContext, AuditService


def get_audit_service() -> AuditService:
    return AuditService()


async def get_audit_context(
    request: Request,
    clock: Annotated[Clock, Depends(get_clock)],
    user: Annotated[dict | None, Depends(get_optional_user)],
) -> AuditContext:
    return AuditContext.from_request(request, user["id"] if user else None, clock)


async def get_system_audit_context(request: Request, clock: Annotated[Clock, Depends(get_clock)]) -> AuditContext:
    """For webhooks with no session (and so no CSRF token): the caller names the acting user."""
    return AuditContext.from_request(request, None, clock)


AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
AuditContextDep = Annotated[AuditContext, Depends(get_audit_context)]
SystemAuditContextDep = Annotated[AuditContext, Depends(get_system_audit_context)]
