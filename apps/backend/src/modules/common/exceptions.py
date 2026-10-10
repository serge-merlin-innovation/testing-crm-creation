class DomainError(Exception):
    pass


class ResourceNotFoundError(DomainError):
    pass


class ResourceExistsError(DomainError):
    pass


class ValidationError(DomainError):
    """Its message is shown to the user as is; `field` names the input it is about."""

    def __init__(self, message: str = "", field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class PermissionDeniedError(DomainError):
    pass


class UserNotFoundError(ResourceNotFoundError):
    pass


class UserExistsError(ResourceExistsError):
    pass


class RoleNotFoundError(ResourceNotFoundError):
    pass


class InsufficientCreditsError(DomainError):
    pass


class LastAdminError(PermissionDeniedError):
    pass


class OneRolePerUserError(ResourceExistsError):
    pass


class PicklistValueNotFoundError(ResourceNotFoundError):
    pass


class PicklistValueExistsError(ResourceExistsError):
    pass


class PicklistValueInUseError(ResourceExistsError):
    pass


class CompanyNotFoundError(ResourceNotFoundError):
    pass


class ContactNotFoundError(ResourceNotFoundError):
    pass


class GroupLoopError(ValidationError):
    pass


class DealNotFoundError(ResourceNotFoundError):
    """Also raised for a deal that exists but is hidden from the caller, so a 404 never confirms it."""


class DealForbiddenError(PermissionDeniedError):
    pass


class DealClosedError(DealForbiddenError):
    pass


class StageCriterionExistsError(ResourceExistsError):
    pass


class StageCriterionNotFoundError(ResourceNotFoundError):
    pass


class MilestoneNotFoundError(ResourceNotFoundError):
    pass


class MandateExistsError(ResourceExistsError):
    pass


class LastLeadPartnerError(ResourceExistsError):
    pass


class TeamMemberNotFoundError(ResourceNotFoundError):
    pass


class TeamMemberExistsError(ResourceExistsError):
    pass


class DealLinkNotFoundError(ResourceNotFoundError):
    pass


class ActivityNotFoundError(ResourceNotFoundError):
    pass


class RestoreWindowClosedError(ResourceExistsError):
    pass


class TaskNotFoundError(ResourceNotFoundError):
    pass


class InvoiceNotFoundError(ResourceNotFoundError):
    pass
