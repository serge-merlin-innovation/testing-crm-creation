from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    link: Mapped[str | None] = mapped_column(String(400), default=None)
    # Set for deal notifications: the list hides them once the reader loses access to the deal.
    mandate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mandates.id", ondelete="CASCADE"), index=True, default=None
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
