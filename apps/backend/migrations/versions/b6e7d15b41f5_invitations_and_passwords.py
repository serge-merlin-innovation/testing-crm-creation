"""Invitations, password policy, password history and reset links

Revision ID: b6e7d15b41f5
Revises: 0e09d7717140
Create Date: 2026-10-10 04:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e7d15b41f5"
down_revision: str | Sequence[str] | None = "0e09d7717140"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("first_name", sa.String(length=50), nullable=True))
    op.add_column("user", sa.Column("last_name", sa.String(length=50), nullable=True))
    op.add_column("user", sa.Column("title", sa.String(length=100), nullable=True))
    op.add_column("user", sa.Column("status", sa.String(length=16), nullable=False, server_default="active"))
    op.add_column("user", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])

    op.create_table(
        "password_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("hashed_password", sa.String(length=100), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_history_user_id", "password_history", ["user_id"])
    op.create_index("ix_password_history_user_id_at", "password_history", ["user_id", "set_at"])

    op.create_table(
        "password_policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("min_length", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("history_count", sa.Integer(), nullable=False, server_default="5"),
    )

    op.create_table(
        "password_reset_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_reset_requests_email_at", "password_reset_requests", ["email", "at"])


def downgrade() -> None:
    op.drop_table("password_reset_requests")
    op.drop_table("password_policy")
    op.drop_table("password_history")
    op.drop_table("account_tokens")
    for column in ("invited_at", "status", "title", "last_name", "first_name"):
        op.drop_column("user", column)
