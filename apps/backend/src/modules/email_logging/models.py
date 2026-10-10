from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class LoggingAddress(Base):
    """A user's personal CRM logging address: `<token>@INBOUND_EMAIL_DOMAIN`."""

    __tablename__ = "email_logging_addresses"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, unique=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LoggedEmail(Base):
    """An inbound email logged as an activity. Attachments: names only, the files are dropped (ACT-04 c5)."""

    __tablename__ = "logged_emails"
    __table_args__ = (Index("ix_logged_emails_message", "user_id", "message_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    attachment_names: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UnmatchedEmail(Base):
    """An email from a CRM user that matched no contact: waits in that user's Unmatched inbox."""

    __tablename__ = "unmatched_emails"
    __table_args__ = (Index("ix_unmatched_emails_message", "user_id", "message_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str] = mapped_column(String(254), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    correspondents: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    attachment_names: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set when the subject named a deal the user is staffed on; linked along with the user's choice.
    mandate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mandates.id", ondelete="SET NULL"), index=True, default=None
    )
