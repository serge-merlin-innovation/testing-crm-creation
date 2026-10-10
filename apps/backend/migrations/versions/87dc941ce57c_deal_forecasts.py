"""deal forecasts

Revision ID: 87dc941ce57c
Revises: b32b7af0bfc9
Create Date: 2026-10-10 14:24:48.967144

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "87dc941ce57c"
down_revision: str | Sequence[str] | None = "b32b7af0bfc9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "deal_forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Integer(), nullable=True),
        sa.Column("expected_closing_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deal_forecasts_mandate_id"), "deal_forecasts", ["mandate_id"], unique=True)
    op.create_index(op.f("ix_deal_forecasts_updated_by"), "deal_forecasts", ["updated_by"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_deal_forecasts_updated_by"), table_name="deal_forecasts")
    op.drop_index(op.f("ix_deal_forecasts_mandate_id"), table_name="deal_forecasts")
    op.drop_table("deal_forecasts")
