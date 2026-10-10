import importlib
import pkgutil

import src.modules
from src.infrastructure.database.session import Base
from src.modules.merge.schemas import MergeableType
from src.modules.merge.service import REFERENCES

TARGETS = {"contacts": MergeableType.CONTACT, "companies": MergeableType.COMPANY}

# Tables that point at a contact or company on purpose but must not follow a merge.
EXEMPT: set[tuple[str, str]] = {
    ("audit_log", "record_id"),
    ("record_merges", "survivor_id"),
}


def _load_models() -> None:
    for module in pkgutil.walk_packages(src.modules.__path__, "src.modules."):
        if module.name.endswith(".models"):
            importlib.import_module(module.name)


def test_every_column_pointing_at_a_mergeable_record_is_in_references() -> None:
    _load_models()
    covered = {(kind, ref.table.name, ref.column) for kind, refs in REFERENCES.items() for ref in refs}
    missing = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                kind = TARGETS.get(fk.column.table.name)
                if kind and (table.name, column.name) not in EXEMPT and (kind, table.name, column.name) not in covered:
                    missing.append(f"{table.name}.{column.name} -> {fk.column.table.name}")
        if "record_type" in table.columns and "record_id" in table.columns and (table.name, "record_id") not in EXEMPT:
            for kind in TARGETS.values():
                if (kind, table.name, "record_id") not in covered:
                    missing.append(f"{table.name}.record_id ({kind.value})")
    assert not missing, f"Add these to merge REFERENCES (or EXEMPT): {missing}"
