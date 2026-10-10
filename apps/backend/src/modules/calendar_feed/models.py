from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class CalendarFeed(Base):
    """A user's private iCal feed. The token is the only credential: regenerating it kills the old URL."""

    __tablename__ = "calendar_feeds"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, unique=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
