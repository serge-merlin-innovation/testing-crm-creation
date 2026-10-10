from typing import Any

from fastapi import APIRouter, Response

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..security.dependencies import StepUpUserDep
from .dependencies import AccessServiceDep
from .schemas import (
    AccessDecision,
    AccessRequestContext,
    AccessRequestCreate,
    AccessRequestItem,
    AccessReviewRead,
    AccessReviewSubmit,
    BreakGlassCreate,
    BreakGlassRead,
    CommentCreate,
    DelegationCreate,
    DelegationRead,
    MyAccessRequest,
)

requests_router = APIRouter(tags=["Wall crossing"])
delegations_router = APIRouter(tags=["Wall crossing"])
break_glass_router = APIRouter(tags=["Wall crossing"])
reviews_router = APIRouter(tags=["Wall crossing"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Not found, or not yours to see"}}


@requests_router.post(
    "/",
    status_code=201,
    response_model=MyAccessRequest,
    summary="Ask to join a deal by its code name",
    description="The deal partner (and their delegate) can comment; compliance decides. 404 for an unknown code name.",
    responses={404: {"description": "No open deal has this code name"}, 409: {"description": "Already staffed or asked"}},
)
async def create_request(
    values: AccessRequestCreate, db: AsyncSessionDep, service: AccessServiceDep, context: AuditContextDep, _: CurrentUserDep
) -> dict[str, Any]:
    return await service.request(db, values, context)


@requests_router.get("/mine", response_model=list[MyAccessRequest], summary="My wall-crossing requests")
async def my_requests(db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep) -> list[dict[str, Any]]:
    return await service.mine(db, user)


@requests_router.get(
    "/",
    response_model=list[AccessRequestItem],
    summary="Pending requests I approve",
    description="Compliance sees all; a deal partner or active delegate sees the ones sent to them.",
)
async def approval_queue(
    db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await service.queue(db, user, clock.now())


@requests_router.get(
    "/{request_id}",
    response_model=AccessRequestContext,
    summary="The approval context of one request",
    description="Never the deal itself. `conflicts` lists the requester's deals on the other side, for compliance only.",
    responses=NOT_FOUND,
)
async def get_request(
    request_id: int, db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep, clock: ClockDep
) -> dict[str, Any]:
    return await service.context(db, user, request_id, clock.now())


@requests_router.post(
    "/{request_id}/comments",
    status_code=201,
    response_model=AccessRequestContext,
    summary="Comment or recommend (deal partner, delegate, compliance)",
    description="A delegate's comment is recorded on behalf of the partner.",
    responses=NOT_FOUND,
)
async def comment_request(
    request_id: int,
    values: CommentCreate,
    db: AsyncSessionDep,
    service: AccessServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.comment(db, user, request_id, values, context)


@requests_router.post(
    "/{request_id}/decision",
    response_model=AccessRequestContext,
    summary="Approve or reject (compliance)",
    description="Approval staffs the requester until `expires_at` (default 30 days). Rejection needs a reason.",
    responses={**NOT_FOUND, 403: {"description": "Only compliance decides"}},
)
async def decide_request(
    request_id: int,
    values: AccessDecision,
    db: AsyncSessionDep,
    service: AccessServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.decide(db, user, request_id, values, context)


@delegations_router.get("/", response_model=list[DelegationRead], summary="My current and upcoming delegations")
async def list_delegations(
    db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await service.delegations(db, user, clock.now().date())


@delegations_router.post(
    "/",
    status_code=201,
    response_model=DelegationRead,
    summary="Delegate my approvals for a date range",
    description="Requests arriving in the range go to the delegate and to me. Both dates are inclusive.",
)
async def create_delegation(
    values: DelegationCreate, db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.delegate(db, user, values, context)


@delegations_router.delete("/{delegation_id}", status_code=204, summary="End a delegation", responses=NOT_FOUND)
async def delete_delegation(
    delegation_id: int, db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep, context: AuditContextDep
) -> Response:
    await service.end_delegation(db, user, delegation_id, context)
    return Response(status_code=204)


@break_glass_router.post(
    "/",
    status_code=201,
    response_model=BreakGlassRead,
    summary="Emergency read access to a deal (Admin)",
    description="Needs a reason and the current 2FA code in X-Step-Up-Code. Read-only, no exports, for 4 hours. "
    "Compliance and the deal partner are notified.",
    responses={401: {"description": "Code missing or wrong"}, 403: {"description": "Admins only"}},
)
async def break_glass(
    values: BreakGlassCreate, db: AsyncSessionDep, service: AccessServiceDep, user: StepUpUserDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.break_glass(db, user, values, context)


@reviews_router.get(
    "/",
    response_model=list[AccessReviewRead],
    summary="Quarterly team reviews",
    description="A partner sees theirs, with the team to confirm; compliance sees every review and its escalation.",
)
async def list_reviews(
    db: AsyncSessionDep, service: AccessServiceDep, user: CurrentUserDep, clock: ClockDep
) -> list[dict[str, Any]]:
    return await service.reviews(db, user, clock.now())


@reviews_router.post(
    "/{review_id}",
    response_model=AccessReviewRead,
    summary="Confirm the team, removing the listed users",
    responses=NOT_FOUND,
)
async def submit_review(
    review_id: int,
    values: AccessReviewSubmit,
    db: AsyncSessionDep,
    service: AccessServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.submit_review(db, user, review_id, values, context)
