import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import src.modules.common.exceptions as exceptions_module
from src.modules.common.constants import EXCEPTION_MAPPING, GENERIC_ERROR_MESSAGE
from src.modules.common.exceptions import (
    InsufficientCreditsError,
    ResourceNotFoundError,
    ValidationError,
)
from src.modules.common.utils.error_handler import (
    _generate_support_id,
    handle_exception,
    map_exception,
    register_exception_handlers,
)


def test_generate_support_id_length():
    support_id = _generate_support_id()
    assert len(support_id) == 8


def test_generate_support_id_unique():
    ids = {_generate_support_id() for _ in range(100)}
    assert len(ids) == 100


def _create_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def raise_not_found():
        raise ResourceNotFoundError("User 123 not found")

    @app.get("/validation")
    async def raise_validation():
        raise ValidationError("name must be at least 2 chars")

    @app.get("/credits")
    async def raise_credits():
        raise InsufficientCreditsError("You need 50 more credits")

    @app.get("/unhandled")
    async def raise_unhandled():
        raise RuntimeError("unexpected internal failure")

    return app


@pytest.fixture
def test_app():
    return _create_test_app()


@pytest.mark.asyncio
async def test_domain_error_returns_generic_message(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/not-found")

    assert response.status_code == 404
    body = response.json()
    assert "User 123" not in body["detail"]
    assert body["detail"] == GENERIC_ERROR_MESSAGE
    assert "support_id" in body
    assert len(body["support_id"]) == 8


@pytest.mark.asyncio
async def test_insufficient_credits_preserves_message(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/credits")

    assert response.status_code == 402
    body = response.json()
    assert "50 more credits" in body["detail"]
    assert "support_id" in body


@pytest.mark.asyncio
async def test_unhandled_error_returns_generic_500(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/unhandled")

    assert response.status_code == 500
    body = response.json()
    assert "unexpected internal failure" not in body["detail"]
    assert body["detail"] == GENERIC_ERROR_MESSAGE
    assert "support_id" in body


def test_map_exception_not_found_uses_generic_detail():
    exc = ResourceNotFoundError("User 42 has secret internal ID xyz")
    http_exc = map_exception(exc)
    assert http_exc.status_code == 404
    assert "User 42" not in http_exc.detail
    assert "secret" not in http_exc.detail
    assert "not found" in http_exc.detail.lower()


def test_map_exception_insufficient_credits_preserves_detail():
    exc = InsufficientCreditsError("You need 50 more credits")
    http_exc = map_exception(exc)
    assert http_exc.status_code == 402
    assert "50 more credits" in http_exc.detail


def test_handle_exception_returns_generic_for_domain_errors():
    exc = ResourceNotFoundError("Payment record #123 not found in DB")
    http_exc = handle_exception(exc)
    assert http_exc is not None
    assert http_exc.status_code == 404
    assert "Payment record #123" not in http_exc.detail


def test_every_domain_exception_has_an_http_mapping():
    """A new domain exception ships with its EXCEPTION_MAPPING entry.

    Without one the exception falls through to the generic handler and the caller gets a 500
    instead of the status the domain meant.
    """
    declared = {
        name
        for name, value in vars(exceptions_module).items()
        if isinstance(value, type) and issubclass(value, Exception) and value.__module__ == exceptions_module.__name__
    }
    mapped = {exception.__name__ for exception in EXCEPTION_MAPPING}
    unmapped = sorted(declared - mapped - {"DomainError"})

    assert not unmapped, (
        f"{unmapped} are declared in common/exceptions.py with no EXCEPTION_MAPPING entry in "
        f"common/constants.py. Raising one would return 500 rather than its intended status."
    )
