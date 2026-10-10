from datetime import datetime
from typing import Any

from sqlalchemy import DDL, JSON, Boolean, DateTime, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.session import Base
from ..company.models import Company
from ..contact.models import Contact
from ..mandate.models import Mandate

# Mirrored by the search migration. `unaccent` is only STABLE, so an index needs this IMMUTABLE
# wrapper pinned to the unaccent dictionary.
SEARCH_FUNCTIONS = (
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS unaccent",
    "CREATE OR REPLACE FUNCTION crm_fold(value text) RETURNS text "
    "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
    "AS $$ SELECT lower(public.unaccent('public.unaccent'::regdictionary, value)) $$",
)

# Every expression `SearchService` matches with `<%`, so each one is served by a trigram index.
SEARCH_INDEXES: dict[str, list[tuple[str, str]]] = {
    "companies": [("ix_companies_name_trgm", "crm_fold(name)")],
    "contacts": [
        ("ix_contacts_full_name_trgm", "crm_fold(first_name || ' ' || last_name)"),
        ("ix_contacts_email_trgm", "crm_fold(coalesce(email, ''))"),
    ],
    "mandates": [("ix_mandates_code_name_trgm", "crm_fold(code_name)")],
}


def index_statements(table: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({expression} gin_trgm_ops)"
        for name, expression in SEARCH_INDEXES[table]
    ]


for _statement in SEARCH_FUNCTIONS:
    event.listen(Base.metadata, "before_create", DDL(_statement).execute_if(dialect="postgresql"))
for _model in (Company, Contact, Mandate):
    for _statement in index_statements(_model.__tablename__):
        event.listen(_model.__table__, "after_create", DDL(_statement).execute_if(dialect="postgresql"))


class SavedFilter(Base):
    """A named set of search criteria. Shared filters are listed for every user; only the owner edits."""

    __tablename__ = "saved_filters"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
