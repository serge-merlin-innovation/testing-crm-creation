"""fees invoices

Revision ID: b3f5916e42d1
Revises: 4969f590271f
Create Date: 2026-10-10 09:32:54.332038

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f5916e42d1"
down_revision: str | Sequence[str] | None = "4969f590271f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fee_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("retainer_monthly", sa.Numeric(14, 2), nullable=False),
        sa.Column("success_fee_kind", sa.String(length=16), nullable=False),
        sa.Column("minimum_fee", sa.Numeric(14, 2), nullable=False),
        sa.Column("retainers_creditable", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("success_fee_percent", sa.Numeric(6, 3), nullable=True),
        sa.Column("success_fee_fixed", sa.Numeric(14, 2), nullable=True),
        sa.Column("lehman_tiers", sa.JSON(), nullable=False),
        sa.Column("final_fee", sa.Numeric(14, 2), nullable=True),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fee_terms_mandate_id"), "fee_terms", ["mandate_id"], unique=True)
    op.create_index(op.f("ix_fee_terms_updated_by"), "fee_terms", ["updated_by"], unique=False)
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("sent_date", sa.Date(), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invoices_mandate_id"), "invoices", ["mandate_id"], unique=False)
    op.create_index(op.f("ix_invoices_recorded_by"), "invoices", ["recorded_by"], unique=False)
    op.create_table(
        "invoice_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invoice_tasks_mandate_id"), "invoice_tasks", ["mandate_id"], unique=False)
    op.create_index(op.f("ix_invoice_tasks_task_id"), "invoice_tasks", ["task_id"], unique=False)
    # Existing installs: give fees.read to the seeded roles that already see fees (role table).
    # Plain SQL so `alembic upgrade --sql` (offline) emits it too.
    op.execute(
        "UPDATE roles SET permissions = (permissions::jsonb || '[\"fees.read\"]'::jsonb)::json "
        "WHERE name IN ('Partner', 'Compliance / Back-office') AND NOT permissions::jsonb @> '[\"fees.read\"]'::jsonb"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_invoice_tasks_task_id"), table_name="invoice_tasks")
    op.drop_index(op.f("ix_invoice_tasks_mandate_id"), table_name="invoice_tasks")
    op.drop_table("invoice_tasks")
    op.drop_index(op.f("ix_invoices_recorded_by"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_mandate_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_fee_terms_updated_by"), table_name="fee_terms")
    op.drop_index(op.f("ix_fee_terms_mandate_id"), table_name="fee_terms")
    op.drop_table("fee_terms")
