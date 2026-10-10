"""drop conflicts approve

Revision ID: df644f9c15bf
Revises: ab9559648858
Create Date: 2026-10-10 20:04:45

"""

from collections.abc import Sequence

from alembic import op

revision: str = "df644f9c15bf"
down_revision: str | Sequence[str] | None = "ab9559648858"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE roles SET permissions = (permissions::jsonb - 'conflicts.approve')::json")


def downgrade() -> None:
    op.execute(
        """UPDATE roles SET permissions = (permissions::jsonb || '["conflicts.approve"]'::jsonb)::json
           WHERE name = 'Partner' AND NOT permissions::jsonb ? 'conflicts.approve'"""
    )
