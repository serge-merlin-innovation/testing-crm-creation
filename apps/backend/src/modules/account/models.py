from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class AccountToken(Base):
    """Single-use invitation and reset links. Only the SHA-256 of the token is stored."""

    __tablename__ = "account_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class PasswordHistory(Base):
    __tablename__ = "password_history"
    __table_args__ = (Index("ix_password_history_user_id_at", "user_id", "set_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordPolicy(Base):
    __tablename__ = "password_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=True)
    min_length: Mapped[int] = mapped_column(Integer, default=12)
    history_count: Mapped[int] = mapped_column(Integer, default=5)


class PasswordResetRequest(Base):
    """Every accepted Forgot password request, by email whether or not it is an account, for the hourly limit."""

    __tablename__ = "password_reset_requests"
    __table_args__ = (Index("ix_password_reset_requests_email_at", "email", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    email: Mapped[str] = mapped_column(String(254))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
