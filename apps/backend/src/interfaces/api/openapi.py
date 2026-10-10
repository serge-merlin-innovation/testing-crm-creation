"""The published OpenAPI document (NFR-05).

Every JSON request body and success response carries an example. Where a route did not write one,
it is derived from the schema, so a new endpoint is documented with an example the day it ships.
"""

from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .versions import API_VERSIONS

SAMPLE_STRINGS = {
    "date-time": "2026-10-10T09:00:00Z",
    "date": "2026-10-10",
    "email": "anna@firm.be",
    "uri": "https://vdr.example.com/falcon",
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
}
MAX_DEPTH = 6


def example_for(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        return None
    if "$ref" in schema:
        return example_for(components.get(schema["$ref"].split("/")[-1], {}), components, depth + 1)
    for key in ("example", "default"):
        if key in schema and schema[key] is not None:
            return schema[key]
    if schema.get("examples"):
        return schema["examples"][0]
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [option for option in schema[key] if option.get("type") != "null"] or schema[key]
            return example_for(options[0], components, depth + 1)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if properties:
            return {name: example_for(sub, components, depth + 1) for name, sub in properties.items()}
        extra = schema.get("additionalProperties")
        return {"key": example_for(extra, components, depth + 1)} if isinstance(extra, dict) else {}
    if kind == "array":
        return [example_for(schema.get("items", {}), components, depth + 1)]
    if kind == "integer":
        return max(1, schema.get("minimum", 1))
    if kind == "number":
        return 25000.0
    if kind == "boolean":
        return True
    if kind == "string":
        return SAMPLE_STRINGS.get(schema.get("format", ""), schema.get("title", "text").lower().replace(" ", "_"))
    return None


def _fill(media: dict[str, Any], components: dict[str, Any]) -> None:
    if "example" in media or "examples" in media or "schema" not in media:
        return
    media["example"] = example_for(media["schema"], components)


def add_examples(spec: dict[str, Any]) -> dict[str, Any]:
    spec = deepcopy(spec)
    components = spec.get("components", {}).get("schemas", {})
    for operations in spec.get("paths", {}).values():
        for operation in operations.values():
            for media in operation.get("requestBody", {}).get("content", {}).values():
                _fill(media, components)
            for status, response in operation.get("responses", {}).items():
                if str(status).startswith("2"):
                    for media in response.get("content", {}).values():
                        _fill(media, components)
    return spec


def build_openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema is None:
        spec = get_openapi(
            title=app.title,
            version=app.version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
            contact=app.contact,
            license_info=app.license_info,
        )
        spec["components"] = spec.get("components", {})
        spec["components"]["securitySchemes"] = {
            "apiToken": {"type": "http", "scheme": "bearer", "description": "Personal API token from the CRM"},
            "oauth2": {
                "type": "oauth2",
                "flows": {"clientCredentials": {"tokenUrl": "/api/v1/oauth/token", "scopes": {}}},
            },
        }
        spec["security"] = [{"apiToken": []}, {"oauth2": []}]
        spec["x-api-versions"] = [version.describe() for version in API_VERSIONS]
        app.openapi_schema = add_examples(spec)
    return app.openapi_schema
