from collections.abc import Callable

from ...infrastructure.auth.http_exceptions import (
    DuplicateValueException,
    ForbiddenException,
    HTTPException,
    NotFoundException,
    UnprocessableEntityException,
)
from .exceptions import (
    CompanyNotFoundError,
    ContactNotFoundError,
    DomainError,
    GroupLoopError,
    InsufficientCreditsError,
    LastAdminError,
    OneRolePerUserError,
    PermissionDeniedError,
    PicklistValueExistsError,
    PicklistValueInUseError,
    PicklistValueNotFoundError,
    ResourceExistsError,
    ResourceNotFoundError,
    RoleNotFoundError,
    UserExistsError,
    UserNotFoundError,
    ValidationError,
)

# Generic error message for client-facing responses (never leak internal details)
GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again."
SUPPORT_ID_LENGTH = 8

# Safety limits for queries that could be unbounded
MAX_ENTITLEMENTS_PER_USER = 100
DEFAULT_BATCH_SIZE = 100

# First isinstance match wins, so subclasses come before their bases.
EXCEPTION_MAPPING: dict[type[DomainError], Callable[[str], HTTPException]] = {
    UserExistsError: lambda message: HTTPException(status_code=409, detail="A user with this email already exists."),
    LastAdminError: lambda message: ForbiddenException(detail="The last Admin cannot be removed."),
    OneRolePerUserError: lambda message: HTTPException(status_code=409, detail="A user can hold only one role."),
    PicklistValueInUseError: lambda message: HTTPException(
        status_code=409, detail="This value is in use: rename or deactivate it instead."
    ),
    PicklistValueExistsError: lambda message: HTTPException(status_code=409, detail="A value with this code exists."),
    PicklistValueNotFoundError: lambda message: NotFoundException(detail="Picklist value not found."),
    CompanyNotFoundError: lambda message: NotFoundException(detail="Company not found."),
    ContactNotFoundError: lambda message: NotFoundException(detail="Contact not found."),
    GroupLoopError: lambda message: UnprocessableEntityException(detail=message),
    InsufficientCreditsError: lambda message: HTTPException(status_code=402, detail=message or "Insufficient credits."),
    ResourceNotFoundError: lambda message: NotFoundException(detail="The requested resource was not found."),
    ResourceExistsError: lambda message: DuplicateValueException(detail="This resource already exists."),
    ValidationError: lambda message: UnprocessableEntityException(detail=message),
    PermissionDeniedError: lambda message: ForbiddenException(detail="You don't have permission for this action."),
    UserNotFoundError: lambda message: NotFoundException(detail="User not found."),
    RoleNotFoundError: lambda message: NotFoundException(detail="The requested role was not found."),
}
