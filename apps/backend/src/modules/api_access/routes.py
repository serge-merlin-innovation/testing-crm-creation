from typing import Annotated, Any

from fastapi import APIRouter, Form, Response
from fastapi.responses import JSONResponse

from ...infrastructure.clock import ClockDep
from ...infrastructure.dependencies import AsyncSessionDep
from ..audit.dependencies import AuditContextDep
from .dependencies import ApiAccessServiceDep, SessionUserDep
from .schemas import (
    ApiClientCreate,
    ApiClientIssued,
    ApiClientRead,
    ApiTokenCreate,
    ApiTokenIssued,
    ApiTokenRead,
    OAuthError,
    OAuthToken,
)
from .service import InvalidClientError

tokens_router = APIRouter(tags=["API access"])
clients_router = APIRouter(tags=["API access"])
oauth_router = APIRouter(tags=["API access"])

SESSION_ONLY: dict[int | str, dict[str, Any]] = {
    403: {"description": "Called with an API credential: credentials are managed from a CRM session"}
}


@tokens_router.get("/", response_model=list[ApiTokenRead], summary="My personal API tokens", responses=SESSION_ONLY)
async def list_api_tokens(db: AsyncSessionDep, service: ApiAccessServiceDep, user: SessionUserDep) -> list[dict[str, Any]]:
    return await service.list_tokens(db, user["id"])


@tokens_router.post(
    "/",
    status_code=201,
    response_model=ApiTokenIssued,
    summary="Issue a personal API token",
    description="The token acts as you, with your role and deal teams. Its secret is returned once; store it now.",
    responses=SESSION_ONLY,
)
async def issue_api_token(
    values: ApiTokenCreate, db: AsyncSessionDep, service: ApiAccessServiceDep, user: SessionUserDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.issue_token(db, user["id"], values, context)


@tokens_router.delete("/{token_id}", status_code=204, summary="Revoke a personal API token", responses=SESSION_ONLY)
async def revoke_api_token(
    token_id: int, db: AsyncSessionDep, service: ApiAccessServiceDep, user: SessionUserDep, context: AuditContextDep
) -> Response:
    await service.revoke_token(db, user["id"], token_id, context)
    return Response(status_code=204)


@clients_router.get("/", response_model=list[ApiClientRead], summary="My OAuth 2.0 clients", responses=SESSION_ONLY)
async def list_api_clients(db: AsyncSessionDep, service: ApiAccessServiceDep, user: SessionUserDep) -> list[dict[str, Any]]:
    return await service.list_clients(db, user["id"])


@clients_router.post(
    "/",
    status_code=201,
    response_model=ApiClientIssued,
    summary="Register an OAuth 2.0 client-credentials client",
    description="The client acts as you, with your role and deal teams. Its secret is returned once.",
    responses=SESSION_ONLY,
)
async def create_api_client(
    values: ApiClientCreate, db: AsyncSessionDep, service: ApiAccessServiceDep, user: SessionUserDep, context: AuditContextDep
) -> dict[str, Any]:
    return await service.create_client(db, user["id"], values, context)


@clients_router.delete(
    "/{client_pk}", status_code=204, summary="Delete an OAuth client and revoke its access tokens", responses=SESSION_ONLY
)
async def revoke_api_client(
    client_pk: int, db: AsyncSessionDep, service: ApiAccessServiceDep, user: SessionUserDep, context: AuditContextDep
) -> Response:
    await service.revoke_client(db, user["id"], client_pk, context)
    return Response(status_code=204)


@oauth_router.post(
    "/token",
    response_model=OAuthToken,
    summary="OAuth 2.0 token endpoint (client credentials grant)",
    description="RFC 6749 section 4.4. Form-encoded. The access token expires after `expires_in` seconds.",
    responses={
        400: {"model": OAuthError, "description": "Unsupported grant type"},
        401: {"model": OAuthError, "description": "Unknown client or wrong secret"},
    },
)
async def oauth_token(
    db: AsyncSessionDep,
    service: ApiAccessServiceDep,
    clock: ClockDep,
    grant_type: Annotated[str, Form(examples=["client_credentials"])],
    client_id: Annotated[str, Form(examples=["crm_client_4f2a9c1e7b3d5a6f8e0c1b2a"])],
    client_secret: Annotated[str, Form(examples=["s3cr3t-shown-once"])],
) -> Any:
    if grant_type != "client_credentials":
        return JSONResponse(status_code=400, content={"error": "unsupported_grant_type"})
    try:
        return await service.grant_client_credentials(db, client_id, client_secret, clock.now())
    except InvalidClientError:
        return JSONResponse(status_code=401, content={"error": "invalid_client"})
