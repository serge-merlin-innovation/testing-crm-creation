from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class UserSecurity(Base):
    """Login state kept apart from `user`, so `UserRead` can never leak the TOTP secret."""

    __tablename__ = "user_security"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), primary_key=True, index=True, init=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), default=None)
    last_login_device: Mapped[str | None] = mapped_column(String(200), default=None)
    travel_from: Mapped[date | None] = mapped_column(Date, default=None)
    travel_until: Mapped[date | None] = mapped_column(Date, default=None)


class LoginFailure(Base):
    __tablename__ = "login_failures"
    __table_args__ = (Index("ix_login_failures_user_id_at", "user_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class TrustedDevice(Base):
    __tablename__ = "trusted_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnownLoginMarker(Base):
    """Countries and devices a user has logged in from, to spot a new one."""

    __tablename__ = "known_login_markers"
    __table_args__ = (Index("ix_known_login_markers_unique", "user_id", "kind", "value", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(200))


class SecurityPolicy(Base):
    __tablename__ = "security_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=True)
    trusted_devices_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
