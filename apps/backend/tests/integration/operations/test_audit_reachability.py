"""X-3: every mutating route reaches an audit write, not only takes the audit context.

A static call graph over `src/`: a function audits when its body calls `<...audit...>.record(`,
`audit_export(` or `record_view(`, and a route audits when its endpoint reaches such a function.
Calls resolve by name (method or function), so the graph over-approximates: it misses no audited
path, and a route it flags really never names an audit write on any path.
"""

import ast
import inspect
from pathlib import Path

from src.interfaces.main import app
from tests.integration.operations.test_audit_coverage import NOT_RECORD_CHANGES

SRC = Path(__file__).resolve().parents[3] / "src"
AUDIT_FUNCTIONS = {"audit_export", "record_view"}


def _audits_directly(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in AUDIT_FUNCTIONS
    if isinstance(func, ast.Attribute):
        if func.attr in AUDIT_FUNCTIONS:
            return True
        return func.attr == "record" and "audit" in ast.unparse(func.value).lower()
    return False


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def call_graph() -> tuple[dict[str, set[str]], set[str]]:
    calls: dict[str, set[str]] = {}
    auditing: set[str] = set()
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            targets = calls.setdefault(node.name, set())
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    if _audits_directly(inner):
                        auditing.add(node.name)
                    if name := _called_name(inner):
                        targets.add(name)
    return calls, auditing


def reaches_audit(start: str, calls: dict[str, set[str]], auditing: set[str]) -> bool:
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name in auditing:
            return True
        if name in seen:
            continue
        seen.add(name)
        todo.extend(calls.get(name, ()))
    return False


def mutating_endpoints():
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        candidates = contexts() if contexts else ([route] if hasattr(route, "dependant") else [])
        for candidate in candidates:
            for method in sorted((getattr(candidate, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}):
                yield method, candidate.path, candidate.endpoint


def test_every_mutating_route_reaches_an_audit_write():
    calls, auditing = call_graph()
    missing = [
        f"{method} {path} ({endpoint.__name__})"
        for method, path, endpoint in mutating_endpoints()
        if (method, path) not in NOT_RECORD_CHANGES and not reaches_audit(endpoint.__name__, calls, auditing)
    ]
    assert not missing, "These change records but never call the audit log:\n" + "\n".join(missing)


def test_the_guard_flags_a_route_that_takes_the_context_and_never_records(tmp_path, monkeypatch):
    sample = tmp_path / "routes.py"
    sample.write_text(
        "async def silent(context):\n    return await helper(context)\n"
        "def helper(context):\n    return 1\n"
        "async def loud(context):\n    self.audit.record(None, context, 'x')\n"
    )
    monkeypatch.setattr(inspect.getmodule(call_graph), "SRC", tmp_path)
    calls, auditing = call_graph()
    assert not reaches_audit("silent", calls, auditing)
    assert reaches_audit("loud", calls, auditing)


def test_the_guard_sees_the_routes():
    assert len(list(mutating_endpoints())) > 100
