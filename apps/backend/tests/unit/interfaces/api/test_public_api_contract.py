"""NFR-05 contract: the published OpenAPI spec and the version support window."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from scripts.export_openapi import SPEC_PATH, render
from src.interfaces.api import versions as registry
from src.interfaces.api.versions import API_VERSIONS, MINIMUM_SUPPORT_MONTHS, ApiVersion, add_months
from src.interfaces.main import app
from src.modules.mandate.policy import served_routes

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def operations():
    for path, item in app.openapi()["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


# AC3: covers every endpoint with examples and stays in sync with each release.


def test_the_committed_openapi_spec_matches_the_app():
    assert SPEC_PATH.exists(), "docs/api/openapi.json is missing: run `uv run python -m scripts.export_openapi`"
    assert SPEC_PATH.read_text() == render(), (
        "docs/api/openapi.json is out of date with the API. Run `uv run python -m scripts.export_openapi` and commit it."
    )


def test_the_spec_covers_every_served_api_endpoint():
    documented = {(method.upper(), path) for path, method, _ in operations()}
    served = {(route.method, route.path) for route in served_routes(app.routes) if route.path.startswith("/api/")}
    hooks = {entry for entry in served if entry[1].startswith("/api/v1/test-hooks")}

    assert served - hooks - documented == set()


def test_every_request_body_and_success_response_has_an_example():
    missing = []
    for path, method, operation in operations():
        bodies = list(operation.get("requestBody", {}).get("content", {}).values())
        for status, response in operation.get("responses", {}).items():
            if str(status).startswith("2"):
                bodies += list(response.get("content", {}).values())
        missing += [f"{method.upper()} {path}" for media in bodies if "schema" in media and "example" not in media]

    assert not missing, missing


def test_every_operation_has_a_summary():
    assert [f"{m} {p}" for p, m, op in operations() if not op.get("summary")] == []


def test_the_spec_documents_both_credential_types_and_no_basic_auth():
    schemes = app.openapi()["components"]["securitySchemes"]

    assert schemes["apiToken"]["scheme"] == "bearer"
    assert schemes["oauth2"]["flows"]["clientCredentials"]["tokenUrl"] == "/api/v1/oauth/token"
    assert all(scheme.get("scheme") != "basic" for scheme in schemes.values())


def test_the_openapi_endpoint_serves_the_published_spec():
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["x-api-versions"][0]["version"] == "v1"


# AC5: a breaking change ships as a new version; the old one runs at least 6 months.


def support_violations(versions: tuple[ApiVersion, ...], mounted: set[str]) -> list[str]:
    problems = []
    for older, newer in zip(versions, versions[1:], strict=False):
        if older.deprecated != newer.released:
            problems.append(f"{older.name} must be deprecated on the day {newer.name} is released")
        if older.sunset is None or older.sunset < add_months(newer.released, MINIMUM_SUPPORT_MONTHS):
            problems.append(f"{older.name} must run until at least {add_months(newer.released, MINIMUM_SUPPORT_MONTHS)}")
    for version in versions:
        if (version.sunset is None or version.sunset > datetime.now(UTC).date()) and version.prefix not in mounted:
            problems.append(f"{version.name} is still supported but not mounted")
    if versions and versions[-1].deprecated is not None:
        problems.append("the newest version cannot be deprecated")
    return problems


def mounted_prefixes() -> set[str]:
    return {"/".join(route.path.split("/")[:3]) for route in served_routes(app.routes) if route.path.startswith("/api/")}


def test_every_supported_api_version_is_mounted_and_runs_six_months_after_its_successor():
    assert support_violations(API_VERSIONS, mounted_prefixes()) == []


@pytest.mark.parametrize(
    ("versions", "expected"),
    [
        (
            (
                ApiVersion("v1", date(2026, 1, 1), deprecated=date(2026, 9, 1), sunset=date(2027, 3, 1)),
                ApiVersion("v2", date(2026, 9, 1)),
            ),
            [],
        ),
        (
            (
                ApiVersion("v1", date(2026, 1, 1), deprecated=date(2026, 9, 1), sunset=date(2027, 2, 28)),
                ApiVersion("v2", date(2026, 9, 1)),
            ),
            ["v1 must run until at least 2027-03-01"],
        ),
        (
            (ApiVersion("v1", date(2026, 1, 1)), ApiVersion("v2", date(2026, 9, 1))),
            ["v1 must be deprecated on the day v2 is released", "v1 must run until at least 2027-03-01"],
        ),
    ],
)
def test_the_support_window_guard_rejects_a_short_sunset(versions, expected):
    mounted = {"/api/v1", "/api/v2"}
    assert support_violations(versions, mounted) == expected


def test_the_guard_flags_a_supported_version_that_was_unmounted():
    versions = (
        ApiVersion("v1", date(2026, 1, 1), deprecated=date(2026, 9, 1), sunset=date(2099, 1, 1)),
        ApiVersion("v2", date(2026, 9, 1)),
    )
    assert support_violations(versions, {"/api/v2"}) == ["v1 is still supported but not mounted"]


def test_a_deprecated_version_announces_its_sunset(monkeypatch):
    sunsetting = ApiVersion("v1", date(2026, 1, 1), deprecated=date(2026, 9, 1), sunset=date(2027, 3, 1))
    monkeypatch.setattr(registry, "API_VERSIONS", (sunsetting,))

    response = TestClient(app).get("/api/v1/auth/check-auth")

    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == "2027-03-01"
