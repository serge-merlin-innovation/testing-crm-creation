from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Response

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from ..role.authorization import has_permission, require_permission
from ..role.permissions import Permission
from .dependencies import PrivacyServiceDep
from .schemas import (
    ErasureResult,
    LegalHoldCreate,
    LegalHoldRead,
    RetentionPolicyValues,
    RetentionReviewRead,
    ReviewDecide,
)
from .service import LegalHoldError

router = APIRouter(tags=["Privacy"])

PrivacyManagerDep = Annotated[dict[str, Any], require_permission(Permission.PRIVACY_MANAGE)]


@router.get(
    "/contacts/{contact_id}/export",
    summary="Export person: everything held about one contact as a JSON file (Compliance)",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}}},
)
async def export_person(
    contact_id: int, db: AsyncSessionDep, service: PrivacyServiceDep, context: AuditContextDep, _: PrivacyManagerDep
) -> Response:
    body, filename = await service.export_person(db, contact_id, context)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/contacts/{contact_id}/erase",
    response_model=ErasureResult,
    summary="Erase (anonymise) a contact unless a legal hold applies (Compliance)",
    responses={409: {"description": "Blocked by a legal hold; the detail gives the reason"}},
)
async def erase_contact(
    contact_id: int, db: AsyncSessionDep, service: PrivacyServiceDep, context: AuditContextDep, _: PrivacyManagerDep
) -> ErasureResult:
    try:
        return await service.erase(db, contact_id, context)
    except LegalHoldError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/contacts/{contact_id}/legal-holds", response_model=list[LegalHoldRead], summary="Legal holds on a contact")
async def list_holds(contact_id: int, db: AsyncSessionDep, service: PrivacyServiceDep, _: PrivacyManagerDep) -> list[Any]:
    return await service.holds(db, contact_id)


@router.post(
    "/contacts/{contact_id}/legal-holds",
    status_code=201,
    response_model=LegalHoldRead,
    summary="Put a contact under legal hold, e.g. AML 10-year retention (Compliance)",
)
async def add_hold(
    contact_id: int,
    values: LegalHoldCreate,
    db: AsyncSessionDep,
    service: PrivacyServiceDep,
    context: AuditContextDep,
    _: PrivacyManagerDep,
) -> Any:
    return await service.add_hold(db, contact_id, values, context)


@router.delete("/legal-holds/{hold_id}", status_code=204, summary="Release a legal hold (Compliance)")
async def release_hold(
    hold_id: int, db: AsyncSessionDep, service: PrivacyServiceDep, context: AuditContextDep, _: PrivacyManagerDep
) -> None:
    await service.release_hold(db, hold_id, context)


@router.get("/privacy/retention-policy", response_model=RetentionPolicyValues, summary="Years without interaction")
async def get_retention_policy(db: AsyncSessionDep, service: PrivacyServiceDep, _: PrivacyManagerDep) -> Any:
    policy = await service.policy(db)
    await db.commit()
    return RetentionPolicyValues(inactive_years=policy.inactive_years)


@router.put("/privacy/retention-policy", response_model=RetentionPolicyValues, summary="Change the retention period")
async def put_retention_policy(
    values: RetentionPolicyValues,
    db: AsyncSessionDep,
    service: PrivacyServiceDep,
    context: AuditContextDep,
    _: PrivacyManagerDep,
) -> Any:
    policy = await service.set_policy(db, values, context)
    return RetentionPolicyValues(inactive_years=policy.inactive_years)


@router.get(
    "/privacy/retention-reviews",
    response_model=list[RetentionReviewRead],
    summary="Open keep-or-anonymise questions: mine, or all for compliance",
)
async def list_reviews(db: AsyncSessionDep, service: PrivacyServiceDep, user: CurrentUserDep) -> list[dict[str, Any]]:
    return await service.reviews(db, user, has_permission(user, Permission.PRIVACY_MANAGE))


@router.post(
    "/privacy/retention-reviews/{review_id}",
    status_code=204,
    summary="Keep or anonymise an inactive contact",
    responses={409: {"description": "Anonymising is blocked by a legal hold"}},
)
async def decide_review(
    review_id: int,
    values: ReviewDecide,
    db: AsyncSessionDep,
    service: PrivacyServiceDep,
    user: CurrentUserDep,
    context: AuditContextDep,
) -> None:
    try:
        await service.decide(db, user, review_id, values.decision, context)
    except LegalHoldError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
