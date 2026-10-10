import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit.service import AuditContext, AuditService
from ..common.exceptions import ResourceNotFoundError
from .models import ApiClient, ApiToken
from .schemas import ApiClientCreate, ApiTokenCreate

PERSONAL_PREFIX = "crm_pat_"
ACCESS_PREFIX = "crm_oat_"
CLIENT_ID_PREFIX = "crm_client_"
SHOWN_PREFIX_LENGTH = 12
ACCESS_TOKEN_LIFETIME = timedelta(hours=1)


class KIND:
    PERSONAL = "personal"
    OAUTH = "oauth"


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class InvalidClientError(Exception):
    pass


@dataclass(frozen=True)
class BearerIdentity:
    user_id: int
    token_id: int
    # The rate-limit bucket: one per personal token, one per OAuth client across all its access tokens.
    rate_key: str
    kind: str


class ApiAccessService:
    def __init__(self, audit: AuditService | None = None) -> None:
        self.audit = audit or AuditService()

    async def issue_token(
        self, db: AsyncSession, user_id: int, values: ApiTokenCreate, context: AuditContext
    ) -> dict[str, Any]:
        secret = PERSONAL_PREFIX + secrets.token_urlsafe(32)
        token = ApiToken(
            user_id=user_id,
            kind=KIND.PERSONAL,
            name=values.name,
            prefix=secret[:SHOWN_PREFIX_LENGTH],
            token_hash=digest(secret),
            created_at=context.clock.now(),
        )
        db.add(token)
        await db.flush()
        self.audit.record(
            db, context, "api_token.issue", record_type="api_token", record_id=token.id, new_values={"name": values.name}
        )
        await db.commit()
        return {**_token_fields(token), "token": secret}

    async def list_tokens(self, db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(ApiToken)
            .where(ApiToken.user_id == user_id, ApiToken.kind == KIND.PERSONAL)
            .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
        )
        return [_token_fields(token) for token in rows.scalars()]

    async def revoke_token(self, db: AsyncSession, user_id: int, token_id: int, context: AuditContext) -> None:
        token = await db.get(ApiToken, token_id)
        if token is None or token.user_id != user_id or token.kind != KIND.PERSONAL:
            raise ResourceNotFoundError("API token not found")
        if token.revoked_at is None:
            token.revoked_at = context.clock.now()
            self.audit.record(db, context, "api_token.revoke", record_type="api_token", record_id=token.id)
            await db.commit()

    async def create_client(
        self, db: AsyncSession, user_id: int, values: ApiClientCreate, context: AuditContext
    ) -> dict[str, Any]:
        secret = secrets.token_urlsafe(32)
        client = ApiClient(
            user_id=user_id,
            name=values.name,
            client_id=CLIENT_ID_PREFIX + secrets.token_hex(12),
            secret_hash=digest(secret),
            created_at=context.clock.now(),
        )
        db.add(client)
        await db.flush()
        self.audit.record(
            db, context, "api_client.create", record_type="api_client", record_id=client.id, new_values={"name": values.name}
        )
        await db.commit()
        return {**_client_fields(client), "client_secret": secret}

    async def list_clients(self, db: AsyncSession, user_id: int) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(ApiClient).where(ApiClient.user_id == user_id).order_by(ApiClient.created_at.desc(), ApiClient.id.desc())
        )
        return [_client_fields(client) for client in rows.scalars()]

    async def revoke_client(self, db: AsyncSession, user_id: int, client_pk: int, context: AuditContext) -> None:
        client = await db.get(ApiClient, client_pk)
        if client is None or client.user_id != user_id:
            raise ResourceNotFoundError("API client not found")
        if client.revoked_at is None:
            now = context.clock.now()
            client.revoked_at = now
            tokens = await db.execute(
                select(ApiToken).where(ApiToken.api_client_id == client.id, ApiToken.revoked_at.is_(None))
            )
            for token in tokens.scalars():
                token.revoked_at = now
            self.audit.record(db, context, "api_client.revoke", record_type="api_client", record_id=client.id)
            await db.commit()

    async def grant_client_credentials(
        self, db: AsyncSession, client_id: str, client_secret: str, now: datetime
    ) -> dict[str, Any]:
        client = (await db.execute(select(ApiClient).where(ApiClient.client_id == client_id))).scalar_one_or_none()
        if (
            client is None
            or client.revoked_at is not None
            or not secrets.compare_digest(client.secret_hash, digest(client_secret))
        ):
            raise InvalidClientError()
        secret = ACCESS_PREFIX + secrets.token_urlsafe(32)
        db.add(
            ApiToken(
                user_id=client.user_id,
                kind=KIND.OAUTH,
                name=client.name,
                prefix=secret[:SHOWN_PREFIX_LENGTH],
                token_hash=digest(secret),
                created_at=now,
                api_client_id=client.id,
                expires_at=now + ACCESS_TOKEN_LIFETIME,
            )
        )
        await db.commit()
        return {"access_token": secret, "token_type": "bearer", "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds())}

    async def resolve(self, db: AsyncSession, secret: str, now: datetime) -> BearerIdentity | None:
        token = (
            await db.execute(
                select(ApiToken).where(
                    ApiToken.token_hash == digest(secret),
                    ApiToken.revoked_at.is_(None),
                    or_(ApiToken.expires_at.is_(None), ApiToken.expires_at > now),
                )
            )
        ).scalar_one_or_none()
        if token is None:
            return None
        rate_key = f"client:{token.api_client_id}" if token.api_client_id is not None else f"token:{token.id}"
        return BearerIdentity(user_id=token.user_id, token_id=token.id, rate_key=rate_key, kind=token.kind)


def _token_fields(token: ApiToken) -> dict[str, Any]:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.prefix,
        "created_at": token.created_at,
        "revoked_at": token.revoked_at,
    }


def _client_fields(client: ApiClient) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "client_id": client.client_id,
        "created_at": client.created_at,
        "revoked_at": client.revoked_at,
    }
