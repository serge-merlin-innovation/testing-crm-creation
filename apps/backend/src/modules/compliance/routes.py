from typing import Annotated, Any

from fastapi import APIRouter

from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from ..mandate.policy import ComplianceGrant, ComplianceReadGrant, EditGrant, ReadGrant
from ..role.authorization import require_permission
from ..role.permissions import Permission
from .dependencies import ConflictServiceDep, KycServiceDep
from .schemas import (
    ConflictDecision,
    ConflictDecisionRead,
    ConflictHitRead,
    ConflictReviewItem,
    CounterpartyCreate,
    CounterpartyRead,
    KycRead,
    KycReview,
    Unfreeze,
)

router = APIRouter(tags=["Compliance"])
reviews_router = APIRouter(tags=["Compliance"])

HIDDEN: dict[int | str, dict[str, Any]] = {404: {"description": "Not found, or not visible to you"}}
COMPLIANCE_ONLY: dict[int | str, dict[str, Any]] = {**HIDDEN, 403: {"description": "Compliance only"}}
ComplianceDep = Annotated[dict[str, Any], require_permission(Permission.CONFLICTS_REGISTER)]


@reviews_router.get(
    "/",
    response_model=list[ConflictReviewItem],
    summary="Conflict reviews waiting for a decision",
    description="Compliance only. Oldest first.",
)
async def open_reviews(db: AsyncSessionDep, service: ConflictServiceDep, _: ComplianceDep) -> list[dict[str, Any]]:
    return await service.open_reviews(db)


@router.get(
    "/{mandate_id}/conflicts",
    response_model=list[ConflictHitRead],
    summary="What the deal conflicts with",
    description="Compliance only (AUTHZ-05 c2): the deal team never sees the other deals.",
    responses=COMPLIANCE_ONLY,
)
async def get_conflicts(grant: ComplianceGrant, db: AsyncSessionDep, service: ConflictServiceDep) -> list[dict[str, Any]]:
    return await service.hits(db, grant.mandate.id)


@router.post(
    "/{mandate_id}/conflicts/decision",
    response_model=ConflictDecisionRead,
    summary="Clear or reject the conflict review",
    description="Compliance only. A reason is required; clearing activates the deal, rejecting aborts it.",
    responses=COMPLIANCE_ONLY,
)
async def decide_conflict(
    values: ConflictDecision,
    grant: ComplianceGrant,
    db: AsyncSessionDep,
    service: ConflictServiceDep,
    context: AuditContextDep,
) -> dict[str, Any]:
    return await service.decide(db, grant, values, context)


@router.get(
    "/{mandate_id}/counterparties", response_model=list[CounterpartyRead], summary="Known counterparties", responses=HIDDEN
)
async def get_counterparties(grant: ReadGrant, db: AsyncSessionDep, service: ConflictServiceDep) -> list[dict[str, Any]]:
    return await service.counterparties(db, grant.mandate)


@router.post(
    "/{mandate_id}/counterparties",
    status_code=201,
    response_model=CounterpartyRead,
    summary="Add a counterparty",
    description="Re-runs the conflict check for that party (AUTHZ-05 c6).",
    responses=HIDDEN,
)
async def add_counterparty(
    values: CounterpartyCreate, grant: EditGrant, db: AsyncSessionDep, service: ConflictServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.add_counterparty(db, grant, values, context)


@router.get("/{mandate_id}/kyc", response_model=KycRead, summary="The deal's KYC status", responses=HIDDEN)
async def get_kyc(grant: ComplianceReadGrant, db: AsyncSessionDep, service: KycServiceDep) -> dict[str, Any]:
    return await service.read(db, grant)


@router.post(
    "/{mandate_id}/kyc",
    response_model=KycRead,
    summary="Record the KYC review",
    description="Compliance only. UBO, ID and PEP/sanctions checks approve it; a sanctions hit freezes the deal.",
    responses=COMPLIANCE_ONLY,
)
async def review_kyc(
    values: KycReview, grant: ComplianceGrant, db: AsyncSessionDep, service: KycServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.review(db, grant, values, context)


@router.post(
    "/{mandate_id}/unfreeze",
    response_model=KycRead,
    summary="Unfreeze a deal after a sanctions hit",
    description="Compliance only, with a reason.",
    responses=COMPLIANCE_ONLY,
)
async def unfreeze(
    values: Unfreeze, grant: ComplianceGrant, db: AsyncSessionDep, service: KycServiceDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.unfreeze(db, grant, values, context)
