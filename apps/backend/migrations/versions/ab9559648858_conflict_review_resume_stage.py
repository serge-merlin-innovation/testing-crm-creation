"""conflict review resume stage

Revision ID: ab9559648858
Revises: 2c2b74c8ce6a
Create Date: 2026-10-10 19:24:59.935720

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab9559648858"
down_revision: str | Sequence[str] | None = "2c2b74c8ce6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conflict_reviews", sa.Column("resume_stage", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("conflict_reviews", "resume_stage")
