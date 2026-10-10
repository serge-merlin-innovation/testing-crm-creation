from typing import Annotated, Any

from fastapi import APIRouter, Query

from ...infrastructure.dependencies import AsyncSessionDep, CurrentUserDep
from ..audit.dependencies import AuditContextDep
from .dependencies import ContactServiceDep
from .schemas import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(tags=["Contacts"])


@router.get("/", response_model=list[ContactRead], summary="Contacts by name or email, alphabetical")
async def list_contacts(
    db: AsyncSessionDep,
    service: ContactServiceDep,
    _: CurrentUserDep,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    return await service.search(db, q, limit)


@router.post(
    "/",
    status_code=201,
    response_model=ContactRead,
    summary="Create a contact",
    description="A shared email is saved but flagged in `warnings` with the other contacts' ids.",
)
async def create_contact(
    values: ContactCreate, db: AsyncSessionDep, service: ContactServiceDep, context: AuditContextDep, _: CurrentUserDep
) -> dict[str, Any]:
    return await service.create(db, values, context)


@router.get("/{contact_id}", response_model=ContactRead, summary="A contact with current role and history")
async def get_contact(contact_id: int, db: AsyncSessionDep, service: ContactServiceDep, _: CurrentUserDep) -> dict[str, Any]:
    return await service.detail(db, contact_id)


@router.patch(
    "/{contact_id}", response_model=ContactRead, summary="Update a contact; a new company keeps the old role as history"
)
async def update_contact(
    contact_id: int,
    values: ContactUpdate,
    db: AsyncSessionDep,
    service: ContactServiceDep,
    context: AuditContextDep,
    _: CurrentUserDep,
) -> dict[str, Any]:
    return await service.update(db, contact_id, values, context)
