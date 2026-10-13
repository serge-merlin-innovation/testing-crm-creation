"""conflict check kyc

Revision ID: 4969f590271f
Revises: 8e8925d25945
Create Date: 2026-10-10 09:50:15.031091

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4969f590271f"
down_revision: str | Sequence[str] | None = "8e8925d25945"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fuzzy company-name matching for the conflict check (AUTHZ-05). Azure Flexible Server must allow-list
    # both in `azure.extensions` (infra/parameters/postgres-server.bicepparam).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_table(
        "conflict_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decided_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conflict_reviews_decided_by"), "conflict_reviews", ["decided_by"], unique=False)
    op.create_index(op.f("ix_conflict_reviews_mandate_id"), "conflict_reviews", ["mandate_id"], unique=False)
    op.create_table(
        "deal_counterparties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("added_by", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["added_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deal_counterparties_added_by"), "deal_counterparties", ["added_by"], unique=False)
    op.create_index(op.f("ix_deal_counterparties_company_id"), "deal_counterparties", ["company_id"], unique=False)
    op.create_index(op.f("ix_deal_counterparties_mandate_id"), "deal_counterparties", ["mandate_id"], unique=False)
    op.create_index("ix_deal_counterparties_unique", "deal_counterparties", ["mandate_id", "company_id"], unique=True)
    op.create_table(
        "kyc_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ubo_check", sa.Boolean(), nullable=False),
        sa.Column("id_check", sa.Boolean(), nullable=False),
        sa.Column("pep_sanctions_screening", sa.Boolean(), nullable=False),
        sa.Column("sanctions_hit", sa.Boolean(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_task_for", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kyc_records_approved_at"), "kyc_records", ["approved_at"], unique=False)
    op.create_index(op.f("ix_kyc_records_mandate_id"), "kyc_records", ["mandate_id"], unique=True)
    op.create_index(op.f("ix_kyc_records_reviewer_id"), "kyc_records", ["reviewer_id"], unique=False)
    op.create_table(
        "conflict_hits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("matched_company_id", sa.Integer(), nullable=False),
        sa.Column("other_mandate_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("other_role", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["other_mandate_id"], ["mandates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["conflict_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conflict_hits_company_id"), "conflict_hits", ["company_id"], unique=False)
    op.create_index(op.f("ix_conflict_hits_matched_company_id"), "conflict_hits", ["matched_company_id"], unique=False)
    op.create_index(op.f("ix_conflict_hits_other_mandate_id"), "conflict_hits", ["other_mandate_id"], unique=False)
    op.create_index(op.f("ix_conflict_hits_review_id"), "conflict_hits", ["review_id"], unique=False)
    op.add_column("mandates", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("mandates", sa.Column("conflict_status", sa.String(length=16), server_default="clear", nullable=False))
    op.add_column("mandates", sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_mandates_created_by"), "mandates", ["created_by"], unique=False)
    op.create_foreign_key("fk_mandates_created_by_user", "mandates", "user", ["created_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_mandates_created_by_user", "mandates", type_="foreignkey")
    op.drop_index(op.f("ix_mandates_created_by"), table_name="mandates")
    op.drop_column("mandates", "frozen_at")
    op.drop_column("mandates", "conflict_status")
    op.drop_column("mandates", "created_by")
    op.drop_index(op.f("ix_conflict_hits_review_id"), table_name="conflict_hits")
    op.drop_index(op.f("ix_conflict_hits_other_mandate_id"), table_name="conflict_hits")
    op.drop_index(op.f("ix_conflict_hits_matched_company_id"), table_name="conflict_hits")
    op.drop_index(op.f("ix_conflict_hits_company_id"), table_name="conflict_hits")
    op.drop_table("conflict_hits")
    op.drop_index(op.f("ix_kyc_records_reviewer_id"), table_name="kyc_records")
    op.drop_index(op.f("ix_kyc_records_mandate_id"), table_name="kyc_records")
    op.drop_index(op.f("ix_kyc_records_approved_at"), table_name="kyc_records")
    op.drop_table("kyc_records")
    op.drop_index("ix_deal_counterparties_unique", table_name="deal_counterparties")
    op.drop_index(op.f("ix_deal_counterparties_mandate_id"), table_name="deal_counterparties")
    op.drop_index(op.f("ix_deal_counterparties_company_id"), table_name="deal_counterparties")
    op.drop_index(op.f("ix_deal_counterparties_added_by"), table_name="deal_counterparties")
    op.drop_table("deal_counterparties")
    op.drop_index(op.f("ix_conflict_reviews_mandate_id"), table_name="conflict_reviews")
    op.drop_index(op.f("ix_conflict_reviews_decided_by"), table_name="conflict_reviews")
    op.drop_table("conflict_reviews")
