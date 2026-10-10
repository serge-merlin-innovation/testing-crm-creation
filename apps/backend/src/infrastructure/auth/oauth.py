from typing import Any

from crudauth.exceptions import BadRequestException
from crudauth.oauth import OAuthProviderFactory
from crudauth.oauth.provider import AbstractOAuthProvider
from crudauth.oauth.schemas import OAuthUserInfo
from crudauth.storage import get_session_storage

from ..config.settings import settings

OAUTH_STATE_TTL_SECONDS = 1800

_redirect_base = settings.OAUTH_REDIRECT_BASE_URL.rstrip("/")


class MicrosoftOAuthProvider(AbstractOAuthProvider):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        tenant: str | None = None,
    ):
        # Settings-derived default because OAuthProviderFactory.create_provider only
        # forwards `scopes`; tests pass `tenant` explicitly.
        tenant = tenant or settings.OAUTH_MICROSOFT_TENANT
        authority = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
        super().__init__(
            client_id,
            client_secret,
            redirect_uri,
            scopes=scopes or ["openid", "profile", "email", "User.Read"],
            authorize_endpoint=f"{authority}/authorize",
            token_endpoint=f"{authority}/token",
            userinfo_endpoint="https://graph.microsoft.com/v1.0/me",
            provider_name="microsoft",
        )

    async def process_user_info(self, user_info: dict[str, Any]) -> OAuthUserInfo:
        oid = user_info.get("id")
        if oid is None:
            raise BadRequestException("Microsoft did not return a user id (id).")
        return OAuthUserInfo(
            provider="microsoft",
            provider_user_id=str(oid),
            # Recorded for logging and admin context only - the callback matches on
            # microsoft_id and never consults this address.
            email=user_info.get("mail") or user_info.get("userPrincipalName"),
            email_verified=False,
            name=user_info.get("displayName"),
            given_name=user_info.get("givenName"),
            family_name=user_info.get("surname"),
            picture=None,
            raw_data=user_info,
        )


OAuthProviderFactory.register_provider("microsoft", MicrosoftOAuthProvider)


def _build_provider(name: str, client_id: str, client_secret: str):
    return OAuthProviderFactory.create_provider(
        name,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=f"{_redirect_base}/api/v1/auth/oauth/callback/{name}",
    )


oauth_providers = {
    "microsoft": _build_provider("microsoft", settings.OAUTH_MICROSOFT_CLIENT_ID, settings.OAUTH_MICROSOFT_CLIENT_SECRET),
}

oauth_state_storage = get_session_storage(
    "memory",
    prefix="oauth_state:",
    expiration=OAUTH_STATE_TTL_SECONDS,
)
