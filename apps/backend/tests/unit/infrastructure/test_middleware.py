import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.infrastructure.middleware import SecurityHeadersMiddleware


def _create_app_with_security_headers(environment: str = "development") -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, environment=environment)

    @app.get("/api/v1/users")
    async def api_route():
        return {"users": []}

    @app.get("/static/logo.png")
    async def static_route():
        return {"file": "logo"}

    return app


@pytest.mark.asyncio
async def test_security_headers_present_in_dev():
    app = _create_app_with_security_headers(environment="development")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["x-xss-protection"] == "0"
    assert "camera=()" in resp.headers["permissions-policy"]
    assert "strict-transport-security" not in resp.headers


@pytest.mark.asyncio
async def test_api_responses_are_not_stored():
    app = _create_app_with_security_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_non_api_responses_get_no_cache_control():
    app = _create_app_with_security_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/static/logo.png")

    assert resp.status_code == 200
    assert "cache-control" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_set_in_production():
    app = _create_app_with_security_headers(environment="production")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert "strict-transport-security" in resp.headers
    assert "max-age=" in resp.headers["strict-transport-security"]
    assert "includeSubDomains" in resp.headers["strict-transport-security"]


@pytest.mark.asyncio
async def test_hsts_set_in_staging():
    app = _create_app_with_security_headers(environment="staging")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/users")

    assert "strict-transport-security" in resp.headers
