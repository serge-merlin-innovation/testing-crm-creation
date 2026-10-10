class DomainError(Exception):
    pass


class ResourceNotFoundError(DomainError):
    pass


class ResourceExistsError(DomainError):
    pass


class ValidationError(DomainError):
    pass


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
