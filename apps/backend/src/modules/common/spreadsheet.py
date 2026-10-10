from collections.abc import Iterable, Mapping
from typing import Any

FORMULA_STARTERS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """Quotes a user string that Excel or openpyxl would otherwise run as a formula."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTERS):
        return "'" + value
    return value


def safe_row(values: Iterable[Any]) -> list[Any]:
    return [safe_cell(value) for value in values]


def safe_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: safe_cell(value) for key, value in row.items()}
