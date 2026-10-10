import uuid as uuid_mod

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ....infrastructure.auth.http_exceptions import (
    HTTPException,
)
from ....infrastructure.logging import get_logger
from ..constants import EXCEPTION_MAPPING, GENERIC_ERROR_MESSAGE, SUPPORT_ID_LENGTH
from ..exceptions import (
    DomainError,
    InsufficientCreditsError,
    ValidationError,
)

logger = get_logger()


def _generate_support_id() -> str:
    return str(uuid_mod.uuid4())[:SUPPORT_ID_LENGTH]


def map_exception(error: DomainError) -> HTTPException:
    for exception_class, mapper in EXCEPTION_MAPPING.items():
        if isinstance(error, exception_class):
            return mapper(str(error))

    logger.error(f"Unmapped domain error: {type(error).__name__}: {error}")
    return HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE)


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            support_id = _generate_support_id()
            logger.exception(f"Unhandled error [{support_id}] on {request.method} {request.url.path}: {exc}")
            return JSONResponse(
                status_code=500,
                content={"detail": GENERIC_ERROR_MESSAGE, "support_id": support_id},
            )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_middleware(CatchAllErrorMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        support_id = _generate_support_id()
        logger.warning(f"Validation error [{support_id}] on {request.method} {request.url.path}: {exc.errors()}")
        # Field and message only, never the submitted input, so a form can show the error inline.
        errors = [
            {"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"].removeprefix("Value error, ")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Invalid request. Please check your input and try again.",
                "errors": errors,
                "support_id": support_id,
            },
        )

    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        support_id = _generate_support_id()
        http_exception = map_exception(exc)

        if isinstance(exc, ValidationError):
            # Raised with a message written for the user, naming the field when there is one.
            content: dict[str, object] = {"detail": str(exc), "support_id": support_id}
            if exc.field:
                content["errors"] = [{"field": exc.field, "message": str(exc)}]
            return JSONResponse(status_code=http_exception.status_code, content=content)

        if isinstance(exc, InsufficientCreditsError):
            logger.info(f"Insufficient credits [{support_id}] on {request.method} {request.url.path}: {exc}")
            return JSONResponse(
                status_code=http_exception.status_code,
                content={"detail": http_exception.detail, "support_id": support_id},
            )

        logger.warning(f"Domain error [{support_id}] on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
        return JSONResponse(
            status_code=http_exception.status_code,
            content={"detail": GENERIC_ERROR_MESSAGE, "support_id": support_id},
        )


def handle_exception(error: Exception) -> HTTPException | None:
    if isinstance(error, DomainError):
        return map_exception(error)
    elif isinstance(error, HTTPException):
        return error
    return None
