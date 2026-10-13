"""Companies, contacts, financials and picklists

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-10-10 03:56:03.128282

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b7c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("salutation", sa.String(length=32), nullable=True),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False),
        sa.Column("legal_basis", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contacts_email"), "contacts", ["email"], unique=False)
    op.create_table(
        "picklist_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label_en", sa.String(length=200), nullable=False),
        sa.Column("label_fr", sa.String(length=200), nullable=True),
        sa.Column("label_nl", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_picklist_values_kind_code", "picklist_values", ["kind", "code"], unique=True)
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=True),
        sa.Column("enterprise_number", sa.String(length=10), nullable=True),
        sa.Column("vat_or_registry_number", sa.String(length=64), nullable=True),
        sa.Column("legal_form", sa.String(length=100), nullable=True),
        sa.Column("nace_code", sa.String(length=16), nullable=True),
        sa.Column("address", sa.String(length=400), nullable=True),
        sa.Column("register_source", sa.String(length=16), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["country_id"], ["picklist_values.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sector_id"], ["picklist_values.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enterprise_number"),
    )
    op.create_index(op.f("ix_companies_country_id"), "companies", ["country_id"], unique=False)
    op.create_index(op.f("ix_companies_normalized_name"), "companies", ["normalized_name"], unique=False)
    op.create_index(op.f("ix_companies_parent_id"), "companies", ["parent_id"], unique=False)
    op.create_index(op.f("ix_companies_sector_id"), "companies", ["sector_id"], unique=False)
    op.create_index(op.f("ix_companies_vat_or_registry_number"), "companies", ["vat_or_registry_number"], unique=False)
    op.create_table(
        "company_financials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.Integer(), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("original_currency", sa.String(length=3), nullable=False),
        sa.Column("original_value", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("eur_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_financials_company_id"), "company_financials", ["company_id"], unique=False)
    op.create_index(
        "ix_company_financials_unique", "company_financials", ["company_id", "year", "metric", "source"], unique=True
    )
    op.create_table(
        "contact_employments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("function", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contact_employments_company_id"), "contact_employments", ["company_id"], unique=False)
    op.create_index(op.f("ix_contact_employments_contact_id"), "contact_employments", ["contact_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_contact_employments_contact_id"), table_name="contact_employments")
    op.drop_index(op.f("ix_contact_employments_company_id"), table_name="contact_employments")
    op.drop_table("contact_employments")
    op.drop_index("ix_company_financials_unique", table_name="company_financials")
    op.drop_index(op.f("ix_company_financials_company_id"), table_name="company_financials")
    op.drop_table("company_financials")
    op.drop_index(op.f("ix_companies_vat_or_registry_number"), table_name="companies")
    op.drop_index(op.f("ix_companies_sector_id"), table_name="companies")
    op.drop_index(op.f("ix_companies_parent_id"), table_name="companies")
    op.drop_index(op.f("ix_companies_normalized_name"), table_name="companies")
    op.drop_index(op.f("ix_companies_country_id"), table_name="companies")
    op.drop_table("companies")
    op.drop_index("ix_picklist_values_kind_code", table_name="picklist_values")
    op.drop_table("picklist_values")
    op.drop_index(op.f("ix_contacts_email"), table_name="contacts")
    op.drop_table("contacts")
