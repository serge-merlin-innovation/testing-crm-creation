from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Not unique: a shared address is a warning, not an error.
    email: Mapped[str | None] = mapped_column(String(254), index=True, default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="en")
    salutation: Mapped[str | None] = mapped_column(String(32), default=None)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # GDPR-01 c2: excluded from every mailing, process letters included.
    marketing_opt_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    legal_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="legitimate_interest")
    source: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.id", ondelete="RESTRICT"), index=True, default=None)


class Employment(Base):
    """A contact's function at a company. The open row (end_date null) is the current role."""

    __tablename__ = "contact_employments"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    function: Mapped[str | None] = mapped_column(String(200), default=None)
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)


class RelationshipHolder(Base):
    """A colleague who knows the contact, and how well: 1 acquainted, 2 good, 3 close."""

    __tablename__ = "relationship_holders"
    __table_args__ = (Index("ix_relationship_holders_unique", "contact_id", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    strength: Mapped[int] = mapped_column(SmallInteger, nullable=False)
