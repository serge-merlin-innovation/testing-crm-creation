"""pipeline stage criteria milestones closing

Revision ID: 8e8925d25945
Revises: 9b7a7a2263d1
Create Date: 2026-10-10 08:44:52.924363

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8e8925d25945"
down_revision: str | Sequence[str] | None = "9b7a7a2263d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mandates", sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mandates", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mandates", sa.Column("stage_before_close", sa.String(length=32), nullable=True))
    op.add_column("mandates", sa.Column("final_ev", sa.Numeric(18, 2), nullable=True))
    op.add_column("mandates", sa.Column("buyer", sa.String(length=200), nullable=True))
    op.add_column("mandates", sa.Column("ev_ebitda", sa.Numeric(8, 2), nullable=True))
    op.add_column("mandates", sa.Column("closing_date", sa.Date(), nullable=True))
    op.add_column("mandates", sa.Column("tombstone_allowed", sa.Boolean(), nullable=True))
    op.add_column("mandates", sa.Column("abort_reason", sa.String(length=1000), nullable=True))
    op.create_index(op.f("ix_mandates_closed_at"), "mandates", ["closed_at"], unique=False)
    op.execute("UPDATE mandates SET stage_changed_at = created_at")
    op.create_table(
        "stage_criteria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stage_criteria_unique", "stage_criteria", ["stage", "kind", "value_key"], unique=True)
    op.create_table(
        "deal_milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deal_milestones_mandate_id"), "deal_milestones", ["mandate_id"], unique=False)
    op.create_index(op.f("ix_deal_milestones_planned_date"), "deal_milestones", ["planned_date"], unique=False)


def downgrade() -> None:
    op.drop_table("deal_milestones")
    op.drop_index("ix_stage_criteria_unique", table_name="stage_criteria")
    op.drop_table("stage_criteria")
    op.drop_index(op.f("ix_mandates_closed_at"), table_name="mandates")
    for column in (
        "abort_reason",
        "tombstone_allowed",
        "closing_date",
        "ev_ebitda",
        "buyer",
        "final_ev",
        "stage_before_close",
        "closed_at",
        "stage_changed_at",
    ):
        op.drop_column("mandates", column)
