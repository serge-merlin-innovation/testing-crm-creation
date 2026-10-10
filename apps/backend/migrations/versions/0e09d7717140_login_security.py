"""Two-factor login, lockout, trusted devices, login alerts and travel flag

Revision ID: 0e09d7717140
Revises: d4e5f6a7b8c9
Create Date: 2026-10-10 04:15:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0e09d7717140"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_security",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(length=64), nullable=True),
        sa.Column("last_login_device", sa.String(length=200), nullable=True),
        sa.Column("travel_from", sa.Date(), nullable=True),
        sa.Column("travel_until", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_user_security_user_id", "user_security", ["user_id"])

    op.create_table(
        "login_failures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_failures_user_id", "login_failures", ["user_id"])
    op.create_index("ix_login_failures_user_id_at", "login_failures", ["user_id", "at"])

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])

    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])

    op.create_table(
        "known_login_markers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_known_login_markers_user_id", "known_login_markers", ["user_id"])
    op.create_index("ix_known_login_markers_unique", "known_login_markers", ["user_id", "kind", "value"], unique=True)

    op.create_table(
        "security_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trusted_devices_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    tables = ("security_policy", "known_login_markers", "trusted_devices", "recovery_codes", "login_failures")
    for table in (*tables, "user_security"):
        op.drop_table(table)
