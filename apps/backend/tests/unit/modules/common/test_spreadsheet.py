import ast
from pathlib import Path

import pytest

from src.modules.common.spreadsheet import safe_cell, safe_row

SOURCE = Path(__file__).parents[4] / "src"


@pytest.mark.parametrize("value", ["=HYPERLINK(1)", "+32 2 123", "-1+1", "@SUM(A1)", "\t=1", "\r=1"])
def test_formula_starters_are_quoted(value):
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["Acme", "", "a=b", 42, -3.5, None])
def test_everything_else_is_left_alone(value):
    assert safe_cell(value) == value


def test_safe_row_maps_every_cell():
    assert safe_row(["=1", "ok", 5]) == ["'=1", "ok", 5]


def _writer_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"writerow", "append"}
        and isinstance(getattr(node.func.value, "id", None), str)
        and node.func.value.id in {"writer", "sheet"}
    ]


def test_every_csv_and_sheet_writer_goes_through_safe_row():
    unsafe = []
    for path in SOURCE.rglob("*.py"):
        for call in _writer_calls(ast.parse(path.read_text())):
            argument = call.args[0] if call.args else None
            wrapped = isinstance(argument, ast.Call) and getattr(argument.func, "id", None) in {"safe_row", "safe_dict"}
            if not wrapped:
                unsafe.append(f"{path.relative_to(SOURCE)}:{call.lineno}")
    assert unsafe == []
