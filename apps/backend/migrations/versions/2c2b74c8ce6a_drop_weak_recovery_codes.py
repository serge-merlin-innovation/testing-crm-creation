"""drop weak recovery codes

Revision ID: 2c2b74c8ce6a
Revises: 646a8075b1e6
Create Date: 2026-10-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = "2c2b74c8ce6a"
down_revision: str | Sequence[str] | None = "646a8075b1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Codes issued before this revision are 32-bit and unsalted; an admin 2FA reset issues new ones.
    op.execute("DELETE FROM recovery_codes")


def downgrade() -> None:
    pass
