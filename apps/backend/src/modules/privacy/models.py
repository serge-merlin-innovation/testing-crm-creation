from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class LegalHold(Base):
    """Compliance blocks erasure of a contact, e.g. AML retention, until a date or until released."""

    __tablename__ = "legal_holds"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class RetentionPolicy(Base):
    """One row (id 1): how long a contact may go without interaction before its owner is asked."""

    __tablename__ = "retention_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=True)
    inactive_years: Mapped[int] = mapped_column(Integer, default=5)


class RetentionReview(Base):
    """The owner's keep-or-anonymise question for one inactive contact."""

    __tablename__ = "retention_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    contact_id: Mapped[int] = mapped_column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(16), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
