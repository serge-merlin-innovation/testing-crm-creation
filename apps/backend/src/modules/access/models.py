from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base


class AccessRequest(Base):
    """A user asking to cross the wall onto a deal they know by code name (AUTHZ-04)."""

    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    requester_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), index=True, default=None
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decision_reason: Mapped[str | None] = mapped_column(String(1000), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AccessRequestApprover(Base):
    """Who was asked when the request arrived: the deal partner, and any delegate of theirs in range then."""

    __tablename__ = "access_request_approvers"
    __table_args__ = (Index("ix_access_request_approvers_unique", "request_id", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    request_id: Mapped[int] = mapped_column(ForeignKey("access_requests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True, default=None)
    # Set for a delegate: they act on behalf of this partner while the delegation lasts.
    on_behalf_of_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, default=None
    )
    delegation_id: Mapped[int | None] = mapped_column(
        ForeignKey("delegations.id", ondelete="CASCADE"), index=True, default=None
    )


class AccessRequestComment(Base):
    __tablename__ = "access_request_comments"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    request_id: Mapped[int] = mapped_column(ForeignKey("access_requests.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The partner's view for compliance: approve or reject. Compliance alone decides.
    recommendation: Mapped[str | None] = mapped_column(String(16), default=None)
    on_behalf_of_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, default=None
    )


class Delegation(Base):
    """A partner's approvals also go to a delegate from `starts_on` to `ends_on`, both inclusive (AUTHZ-07)."""

    __tablename__ = "delegations"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    partner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    delegate_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccessReview(Base):
    """The quarterly confirmation of one deal's team by its partner (ADM-05)."""

    __tablename__ = "access_reviews"
    __table_args__ = (Index("ix_access_reviews_unique", "mandate_id", "quarter", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("mandates.id", ondelete="CASCADE"), index=True)
    partner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    quarter: Mapped[str] = mapped_column(String(7), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
