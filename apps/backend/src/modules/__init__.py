"""Import every model so SQLAlchemy registers all application tables."""

from .role.models import Role
from .user.models import User

__all__ = [
    "User",
    "Role",
]
