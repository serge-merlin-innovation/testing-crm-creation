from typing import TYPE_CHECKING

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...infrastructure.database.models import SoftDeleteMixin, TimestampMixin
from ...infrastructure.database.session import Base

if TYPE_CHECKING:
    from ..user.models import User


class Role(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        "id",
        autoincrement=True,
        nullable=False,
        unique=True,
        primary_key=True,
        init=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Reassign a new list to change it: JSON columns do not track in-place mutation.
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default_factory=list)

    users: Mapped[list["User"]] = relationship("User", back_populates="role", lazy="selectin", default_factory=list, init=False)

    def __repr__(self) -> str:
        return self.name
