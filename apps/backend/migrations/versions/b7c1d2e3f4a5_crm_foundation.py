"""CRM foundation: email login, role permissions, append-only audit log

Revision ID: b7c1d2e3f4a5
Revises: a90213be73b8
Create Date: 2026-10-10 03:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "a90213be73b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("roles", sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"))

    # Users with is_superuser get the Admin role. Startup seeding fills in the Admin role's
    # permissions and the other five roles.
    op.execute(
        "INSERT INTO roles (name, description, permissions, created_at, updated_at, is_deleted) "
        "SELECT 'Admin', 'IT / ops configuration', "
        '\'["audit.read", "roles.manage", "settings.manage", "users.manage"]\', now(), now(), false '
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'Admin')"
    )
    op.execute("UPDATE \"user\" SET role_id = (SELECT id FROM roles WHERE name = 'Admin') WHERE is_superuser")

    op.drop_index(op.f("ix_user_microsoft_id"), table_name="user")
    op.drop_index(op.f("ix_user_username"), table_name="user")
    for column in ("username", "is_superuser", "microsoft_id", "oauth_provider", "oauth_created_at", "oauth_updated_at"):
        op.drop_column("user", column)
    op.alter_column("user", "name", type_=sa.String(length=100))
    op.alter_column("user", "email", type_=sa.String(length=254))

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("record_type", sa.String(length=64), nullable=True),
        sa.Column("record_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("old_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_user_id_created_at", "audit_log", ["user_id", "created_at"])
    op.create_index("ix_audit_log_record", "audit_log", ["record_type", "record_id", "created_at"])
    op.create_index("ix_audit_log_action_created_at", "audit_log", ["action", "created_at"])

    # Must match APPEND_ONLY_* in src/modules/audit/models.py.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM CURRENT_USER")


def downgrade() -> None:
    # The audit log is retained 10 years: a downgrade never drops it.
    op.add_column("user", sa.Column("oauth_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("oauth_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user", sa.Column("oauth_provider", sa.String(length=20), nullable=True))
    op.add_column("user", sa.Column("microsoft_id", sa.String(length=50), nullable=True))
    op.add_column("user", sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("username", sa.String(length=254), nullable=True))
    op.execute('UPDATE "user" SET username = email')
    op.alter_column("user", "username", nullable=False)
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)
    op.create_index(op.f("ix_user_microsoft_id"), "user", ["microsoft_id"], unique=True)
    op.drop_column("roles", "permissions")
