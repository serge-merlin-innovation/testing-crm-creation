from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class SessionPolicy(Base):
    """One row (id 1). Read at login: a session keeps the limits it was opened with."""

    __tablename__ = "session_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=True)
    desktop_idle_minutes: Mapped[int] = mapped_column(Integer, default=30)
    mobile_idle_minutes: Mapped[int] = mapped_column(Integer, default=15)
    absolute_hours: Mapped[int] = mapped_column(Integer, default=12)
    mobile_read_only: Mapped[bool] = mapped_column(Boolean, default=False)
