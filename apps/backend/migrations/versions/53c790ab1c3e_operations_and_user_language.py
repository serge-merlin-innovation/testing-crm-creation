"""operations: recovery drills, security findings, maintenance windows; user language

Revision ID: 53c790ab1c3e
Revises: 87dc941ce57c
Create Date: 2026-10-10 15:11:27.478661

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "53c790ab1c3e"
down_revision: str | Sequence[str] | None = "87dc941ce57c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("announced_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["announced_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_maintenance_windows_announced_by"), "maintenance_windows", ["announced_by"], unique=False)
    op.create_index(op.f("ix_maintenance_windows_starts_at"), "maintenance_windows", ["starts_at"], unique=False)
    op.create_table(
        "recovery_drills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("backup_taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_restored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_verified", sa.Boolean(), nullable=False),
        sa.Column("data_loss_hours", sa.Float(), nullable=False),
        sa.Column("recovery_hours", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logged_by", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["logged_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recovery_drills_logged_at"), "recovery_drills", ["logged_at"], unique=False)
    op.create_index(op.f("ix_recovery_drills_logged_by"), "recovery_drills", ["logged_by"], unique=False)
    op.create_index(op.f("ix_recovery_drills_passed"), "recovery_drills", ["passed"], unique=False)
    op.create_table(
        "security_findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fixed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_security_findings_created_by"), "security_findings", ["created_by"], unique=False)
    op.create_index(op.f("ix_security_findings_severity"), "security_findings", ["severity"], unique=False)
    op.create_index(op.f("ix_security_findings_status"), "security_findings", ["status"], unique=False)
    op.add_column("user", sa.Column("language", sa.String(length=2), server_default="en", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user", "language")
    op.drop_index(op.f("ix_security_findings_status"), table_name="security_findings")
    op.drop_index(op.f("ix_security_findings_severity"), table_name="security_findings")
    op.drop_index(op.f("ix_security_findings_created_by"), table_name="security_findings")
    op.drop_table("security_findings")
    op.drop_index(op.f("ix_recovery_drills_passed"), table_name="recovery_drills")
    op.drop_index(op.f("ix_recovery_drills_logged_by"), table_name="recovery_drills")
    op.drop_index(op.f("ix_recovery_drills_logged_at"), table_name="recovery_drills")
    op.drop_table("recovery_drills")
    op.drop_index(op.f("ix_maintenance_windows_starts_at"), table_name="maintenance_windows")
    op.drop_index(op.f("ix_maintenance_windows_announced_by"), table_name="maintenance_windows")
    op.drop_table("maintenance_windows")
