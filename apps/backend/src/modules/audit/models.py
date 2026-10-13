from datetime import datetime
from typing import Any

from sqlalchemy import DDL, JSON, BigInteger, DateTime, Index, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base

RETENTION_YEARS = 10

# Mirrored by the migration that creates the table. The trigger is what makes the table
# append-only for every database role, the table owner included; the migration also REVOKEs
# UPDATE, DELETE and TRUNCATE from the application role.
APPEND_ONLY_FUNCTION = DDL(
    """
    CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_log is append-only';
    END;
    $$ LANGUAGE plpgsql
    """
)
APPEND_ONLY_ROW_TRIGGER = DDL(
    "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON audit_log "
    "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
)
APPEND_ONLY_TRUNCATE_TRIGGER = DDL(
    "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
    "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only()"
)


class AuditEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_user_id_created_at", "user_id", "created_at"),
        Index("ix_audit_log_record", "record_type", "record_id", "created_at"),
        Index("ix_audit_log_action_created_at", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, init=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # No foreign key: an entry must outlive the user row it names.
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    record_type: Mapped[str | None] = mapped_column(String(64), default=None)
    record_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


for _ddl in (APPEND_ONLY_FUNCTION, APPEND_ONLY_ROW_TRIGGER, APPEND_ONLY_TRUNCATE_TRIGGER):
    event.listen(AuditEntry.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))
