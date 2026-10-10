import pytest
from crudauth.exceptions import BadRequestException
from crudauth.oauth import OAuthProviderFactory

from src.infrastructure.auth.oauth import MicrosoftOAuthProvider

TENANT = "11111111-2222-3333-4444-555555555555"


def _provider(tenant: str = TENANT) -> MicrosoftOAuthProvider:
    return MicrosoftOAuthProvider(
        "client-id",
        "client-secret",
        "http://localhost:8000/api/v1/auth/oauth/callback/microsoft",
        tenant=tenant,
    )


def test_provider_is_registered_with_the_factory():
    assert OAuthProviderFactory.get_provider_class("microsoft") is MicrosoftOAuthProvider


def test_endpoints_are_built_from_the_configured_tenant():
    provider = _provider()

    assert provider.authorize_endpoint == f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize"
    assert provider.token_endpoint == f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    assert provider.provider_name == "microsoft"


def test_userinfo_endpoint_is_microsoft_graph():
    assert _provider().userinfo_endpoint == "https://graph.microsoft.com/v1.0/me"


def test_default_scopes_include_graph_user_read():
    assert _provider().scopes == ["openid", "profile", "email", "User.Read"]


def test_scopes_can_be_overridden():
    provider = MicrosoftOAuthProvider("id", "secret", "http://cb", scopes=["openid"], tenant=TENANT)

    assert provider.scopes == ["openid"]


def test_authorization_url_carries_tenant_and_pkce():
    auth_data = _provider().get_authorization_url()

    assert auth_data["url"].startswith(f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize?")
    assert "code_challenge=" in auth_data["url"]
    assert "code_challenge_method=S256" in auth_data["url"]
    assert auth_data["code_verifier"]


@pytest.mark.asyncio
async def test_process_user_info_maps_graph_claims():
    info = await _provider().process_user_info(
        {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "mail": "alice@client.example",
            "userPrincipalName": "alice@client.onmicrosoft.com",
            "displayName": "Alice Adams",
            "givenName": "Alice",
            "surname": "Adams",
        }
    )

    assert info.provider == "microsoft"
    assert info.provider_user_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    # `mail` is the real mailbox; userPrincipalName can be a non-routable #EXT# value.
    assert info.email == "alice@client.example"
    assert info.name == "Alice Adams"
    assert info.given_name == "Alice"
    assert info.family_name == "Adams"
    assert info.raw_data["displayName"] == "Alice Adams"


@pytest.mark.asyncio
async def test_process_user_info_falls_back_to_user_principal_name():
    info = await _provider().process_user_info({"id": "oid-1", "mail": None, "userPrincipalName": "bob@client.onmicrosoft.com"})

    assert info.email == "bob@client.onmicrosoft.com"


@pytest.mark.asyncio
async def test_email_is_never_reported_verified():
    info = await _provider().process_user_info({"id": "oid-1", "mail": "alice@client.example"})

    assert info.email_verified is False


@pytest.mark.asyncio
async def test_missing_user_id_raises():
    with pytest.raises(BadRequestException):
        await _provider().process_user_info({"mail": "alice@client.example"})
