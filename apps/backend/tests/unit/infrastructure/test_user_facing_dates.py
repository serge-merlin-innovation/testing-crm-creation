"""NFR-04 c4: dates in text a user reads are DD/MM/YYYY, never ISO.

The guard fails when an f-string in a module service or job calls `.isoformat()`: route the date through
`format_date(value, language)` instead. Machine payloads (audit values, JSON fields) are not f-strings.
"""

import ast
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.infrastructure.i18n.formatters import format_date

MODULES = Path(__file__).resolve().parents[3] / "src" / "modules"


def _iso_in_fstrings(path: Path) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.JoinedStr):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "isoformat":
                    lines.append(inner.lineno)
    return lines


def test_no_iso_date_in_user_facing_text():
    files = [*MODULES.glob("*/service.py"), *MODULES.glob("*/jobs.py")]
    assert files
    offenders = [f"{path.relative_to(MODULES)}:{line}" for path in files for line in _iso_in_fstrings(path)]
    assert not offenders, f"Use format_date(value, language) for dates shown to users: {offenders}"


def test_the_guard_catches_an_iso_date_in_an_fstring(tmp_path):
    sample = tmp_path / "service.py"
    sample.write_text('def body(d):\n    return f"due {d.isoformat()}"\n')
    assert _iso_in_fstrings(sample) == [2]


@pytest.mark.parametrize("language", ["en", "fr", "nl"])
def test_format_date_is_belgian_in_every_language(language):
    assert format_date(date(2026, 9, 15), language) == "15/09/2026"
    assert format_date(datetime(2026, 9, 14, 23, 30, tzinfo=UTC), language) == "15/09/2026"
