from fastapi import status
from fastapi.exceptions import HTTPException
from fastcrud.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
    RateLimitException,
    UnauthorizedException,
    UnprocessableEntityException,
)

__all__ = [
    "BadRequestException",
    "NotFoundException",
    "ForbiddenException",
    "UnauthorizedException",
    "UnprocessableEntityException",
    "DuplicateValueException",
    "RateLimitException",
    "HTTPException",
    "CSRFException",
]


class CSRFException(HTTPException):
    def __init__(self, detail: str = "CSRF token validation failed"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            headers={"X-CSRF-Error": "true"},
        )
