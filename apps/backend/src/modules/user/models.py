from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base
from ..role.models import Role


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        unique=True,
        primary_key=True,
        init=False,
    )

    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))

    profile_image_url: Mapped[str] = mapped_column(String, default="https://profileimageurl.com")

    # One role per user (AUTHZ-01): a single column, so a second role cannot exist.
    role_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("roles.id"),
        index=True,
        default=None,
    )

    email_verified: Mapped[bool] = mapped_column(default=False)

    first_name: Mapped[str | None] = mapped_column(String(50), default=None)
    last_name: Mapped[str | None] = mapped_column(String(50), default=None)
    title: Mapped[str | None] = mapped_column(String(100), default=None)
    # "invited" until the invitation link is used, then "active". Deactivation is `is_deleted`.
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    role: Mapped["Role | None"] = relationship("Role", back_populates="users", lazy="selectin", init=False)

    # Mapped SQL expressions, not columns - keep out of the `User` schema (`UserService.update`
    # writes via UPDATE ... RETURNING using that schema's field names). `correlate_except` is
    # required or SQLAlchemy correlates `roles` away in `get_joined` queries. No `deferred=True`:
    # FastCRUD's create() reads every column_attrs entry, and a deferred load raises MissingGreenlet.
    role_name: Mapped[str | None] = column_property(
        select(Role.name).where(Role.id == role_id, Role.is_deleted.is_(False)).correlate_except(Role).scalar_subquery()
    )
    permissions: Mapped[Any] = column_property(
        select(Role.permissions).where(Role.id == role_id, Role.is_deleted.is_(False)).correlate_except(Role).scalar_subquery()
    )

    @property
    def is_active(self) -> bool:
        """Map soft deletion onto crudauth's active-user contract."""
        return not self.is_deleted

    def __repr__(self) -> str:
        return f"{self.name} ({self.email})"
