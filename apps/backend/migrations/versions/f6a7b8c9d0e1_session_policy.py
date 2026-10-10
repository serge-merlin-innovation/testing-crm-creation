"""Session timeouts and mobile access policy

Revision ID: f6a7b8c9d0e1
Revises: 0e09d7717140
Create Date: 2026-10-10 04:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "0e09d7717140"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("desktop_idle_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("mobile_idle_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("absolute_hours", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("mobile_read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("session_policy")
