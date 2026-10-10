from collections.abc import Callable

from ...infrastructure.auth.http_exceptions import (
    DuplicateValueException,
    ForbiddenException,
    HTTPException,
    NotFoundException,
    UnprocessableEntityException,
)
from .exceptions import (
    ActivityNotFoundError,
    CompanyNotFoundError,
    ContactNotFoundError,
    DealClosedError,
    DealForbiddenError,
    DealFrozenError,
    DealLinkNotFoundError,
    DealNotFoundError,
    DomainError,
    GroupLoopError,
    ImportNotFoundError,
    InsufficientCreditsError,
    LastAdminError,
    LastLeadPartnerError,
    MandateExistsError,
    MergeBlockedError,
    MergeNotFoundError,
    MilestoneNotFoundError,
    OneRolePerUserError,
    PermissionDeniedError,
    PicklistValueExistsError,
    PicklistValueInUseError,
    PicklistValueNotFoundError,
    ResourceExistsError,
    ResourceNotFoundError,
    RestoreWindowClosedError,
    RoleNotFoundError,
    StageCriterionExistsError,
    StageCriterionNotFoundError,
    TaskNotFoundError,
    TeamMemberExistsError,
    TeamMemberNotFoundError,
    UndoWindowClosedError,
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
    DealNotFoundError: lambda message: NotFoundException(detail="Not found."),
    DealFrozenError: lambda message: ForbiddenException(
        detail="This deal is frozen after a sanctions hit: only compliance can unfreeze it."
    ),
    DealClosedError: lambda message: ForbiddenException(
        detail="This deal is closed and read-only: a partner must reopen it first."
    ),
    StageCriterionExistsError: lambda message: HTTPException(
        status_code=409, detail="This stage already has that exit criterion."
    ),
    StageCriterionNotFoundError: lambda message: NotFoundException(detail="Exit criterion not found."),
    MilestoneNotFoundError: lambda message: NotFoundException(detail="Milestone not found."),
    DealForbiddenError: lambda message: ForbiddenException(detail="You don't have permission for this action on this deal."),
    MandateExistsError: lambda message: HTTPException(status_code=409, detail="This code name is already in use."),
    LastLeadPartnerError: lambda message: HTTPException(
        status_code=409, detail="Every deal needs a lead partner: the last lead partner cannot be removed."
    ),
    TeamMemberExistsError: lambda message: HTTPException(status_code=409, detail="This user is already on the deal team."),
    TeamMemberNotFoundError: lambda message: NotFoundException(detail="This user is not on the deal team."),
    DealLinkNotFoundError: lambda message: NotFoundException(detail="Link not found."),
    ActivityNotFoundError: lambda message: NotFoundException(detail="Activity not found."),
    TaskNotFoundError: lambda message: NotFoundException(detail="Task not found."),
    MergeBlockedError: lambda message: ForbiddenException(
        detail="One of these records is on a deal you cannot access. Ask Compliance to merge them."
    ),
    MergeNotFoundError: lambda message: NotFoundException(detail="Merge not found."),
    UndoWindowClosedError: lambda message: HTTPException(
        status_code=409, detail="This merge was done more than 30 days ago, or was already undone."
    ),
    ImportNotFoundError: lambda message: NotFoundException(detail="Import not found."),
    RestoreWindowClosedError: lambda message: HTTPException(
        status_code=409, detail="This activity was deleted more than 30 days ago and can no longer be restored."
    ),
    GroupLoopError: lambda message: UnprocessableEntityException(detail=message),
    InsufficientCreditsError: lambda message: HTTPException(status_code=402, detail=message or "Insufficient credits."),
    ResourceNotFoundError: lambda message: NotFoundException(detail="The requested resource was not found."),
    ResourceExistsError: lambda message: DuplicateValueException(detail="This resource already exists."),
    ValidationError: lambda message: UnprocessableEntityException(detail=message),
    PermissionDeniedError: lambda message: ForbiddenException(detail="You don't have permission for this action."),
    UserNotFoundError: lambda message: NotFoundException(detail="User not found."),
    RoleNotFoundError: lambda message: NotFoundException(detail="The requested role was not found."),
}
