from typing import Any

from fastapi import APIRouter, Request, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..audit.service import AuditContext
from ..role.authorization import RequireRecordAccess
from .dependencies import EmailLoggingServiceDep, InboundSecretDep
from .schemas import InboundEmail, InboundResult, InteractionRead, LoggingAddressRead, UnmatchedLink, UnmatchedRead
from .service import interactions

router = APIRouter(tags=["Email logging"])


@router.get(
    "/address",
    dependencies=[RequireRecordAccess],
    response_model=LoggingAddressRead,
    summary="My personal CRM logging address",
    description="BCC or forward an email to it to log the email on the matching contacts.",
)
async def my_address(
    db: AsyncSessionDep, service: EmailLoggingServiceDep, user: CurrentUserDep, clock: ClockDep
) -> dict[str, Any]:
    return {"address": await service.address_for(db, user, clock.now())}


@router.post(
    "/inbound",
    status_code=202,
    response_model=InboundResult,
    summary="Mail provider webhook: an email sent to a CRM logging address",
    description=(
        "Called by the inbound-parse adapter with `X-Inbound-Secret`. The sender must be a CRM user writing to "
        "their own logging address (403 otherwise). Matched contacts get the email on their timeline; no match "
        "puts it in the sender's Unmatched inbox. A `[CodeName]` subject links the deal only for its team. "
        "Attachment files are dropped: only names are kept."
    ),
    responses={401: {"description": "Bad webhook secret"}, 403: {"description": "Sender is not a CRM user"}},
)
async def inbound(
    email: InboundEmail,
    db: AsyncSessionDep,
    service: EmailLoggingServiceDep,
    _: InboundSecretDep,
    clock: ClockDep,
    request: Request,
) -> InboundResult:
    # No session lookup: the webhook is authenticated by its secret, and the actor is the sender.
    context = AuditContext.from_request(request, None, clock)
    return await service.receive(db, email, clock.now(), context)


@router.get(
    "/unmatched",
    dependencies=[RequireRecordAccess],
    response_model=list[UnmatchedRead],
    summary="My Unmatched inbox, newest first",
)
async def list_unmatched(db: AsyncSessionDep, service: EmailLoggingServiceDep, user: CurrentUserDep) -> Any:
    return await service.unmatched(db, user)


@router.post(
    "/unmatched/{unmatched_id}/link",
    dependencies=[RequireRecordAccess],
    status_code=201,
    summary="Log an unmatched email on the records I pick",
    description="Linking a deal needs edit access to it. Returns the new activity id.",
)
async def link_unmatched(
    unmatched_id: int,
    values: UnmatchedLink,
    db: AsyncSessionDep,
    service: EmailLoggingServiceDep,
    user: CurrentUserDep,
    clock: ClockDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.link(db, user, unmatched_id, values, clock.now(), context)


@router.delete(
    "/unmatched/{unmatched_id}", dependencies=[RequireRecordAccess], status_code=204, summary="Discard an unmatched email"
)
async def discard_unmatched(
    unmatched_id: int,
    db: AsyncSessionDep,
    service: EmailLoggingServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> Response:
    await service.discard(db, user, unmatched_id, context)
    return Response(status_code=204)


interactions_router = APIRouter(tags=["Contacts"])


@interactions_router.get(
    "/{contact_id}/interactions",
    response_model=list[InteractionRead],
    summary="Who in the firm knows this contact: emails and meetings per colleague",
    description="Count and last interaction date per colleague, most recent first. Deal activities the reader "
    "is not staffed on do not count.",
)
async def contact_interactions(
    contact_id: int, db: AsyncSessionDep, user: CurrentUserDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await interactions(db, user, contact_id, clock.now())
