"""Whether a feature module is wired into the app, plus the dataclass model rules that fail at runtime.

Four of these need the built app, the import system, or the presence of a file — none of which a
linter can see. The three model-declaration rules could have been lint, and are here only because
ruff has no plugin API and its `banned-api` matches an imported name, not a keyword argument on a
call. Every module is discovered by globbing `src/modules/`, so a new feature module is covered the
moment it exists rather than when someone remembers to add it here.
"""

import ast
import importlib
import pkgutil
from functools import cache
from pathlib import Path

import pytest

from src.interfaces.main import app

BACKEND_DIRECTORY = Path(__file__).parents[3]
MODULES_DIRECTORY = BACKEND_DIRECTORY / "src" / "modules"

# `common` is the shared module every other one may import; it has no model, router or service.
SHARED_MODULE = "common"

REQUIRED_MODULE_FILES = (
    "__init__.py",
    "models.py",
    "schemas.py",
    "crud.py",
    "service.py",
    "routes.py",
    "dependencies.py",
)

# A fork whose module legitimately lacks one of the required files adds it here, in the diff, rather
# than reaching for an inline suppression.
OPTIONAL_MODULE_FILES: dict[str, tuple[str, ...]] = {}

HTTP_VERBS = ("get", "post", "patch", "put", "delete")
API_PREFIX = "/api/v1"


def feature_modules() -> list[str]:
    return sorted(
        directory.name
        for directory in MODULES_DIRECTORY.iterdir()
        if directory.is_dir() and not directory.name.startswith("__") and directory.name != SHARED_MODULE
    )


FEATURE_MODULES = feature_modules()


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def is_call_to(node: ast.AST, name: str) -> bool:
    """Matches `name(...)` and `anything.name(...)`, so a fork's `sa.mapped_column` still counts."""
    if not isinstance(node, ast.Call):
        return False
    return (isinstance(node.func, ast.Name) and node.func.id == name) or (
        isinstance(node.func, ast.Attribute) and node.func.attr == name
    )


def calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if is_call_to(node, name)]


def functions_in(tree: ast.AST) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)]


def keyword_of(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def mounted_paths_of(endpoint: str) -> list[str]:
    return [
        path
        for path, operations in app.openapi()["paths"].items()
        for operation in operations.values()
        if operation.get("operationId", "").startswith(f"{endpoint}_")
    ]


@cache
def module_source(module: str, filename: str) -> ast.Module:
    return parse(MODULES_DIRECTORY / module / filename)


class TestEveryFeatureModuleIsWired:
    def test_at_least_one_module_was_discovered(self):
        assert FEATURE_MODULES, f"No feature modules found under {MODULES_DIRECTORY}. The glob or the layout changed."

    @pytest.mark.parametrize("module", FEATURE_MODULES)
    def test_module_ships_every_required_file(self, module: str):
        expected = set(REQUIRED_MODULE_FILES) - set(OPTIONAL_MODULE_FILES.get(module, ()))
        missing = sorted(name for name in expected if not (MODULES_DIRECTORY / module / name).is_file())

        assert not missing, (
            f"modules/{module}/ is missing {missing}. A feature module ships {sorted(expected)}; "
            f"if this module legitimately has no HTTP surface, add the filenames to OPTIONAL_MODULE_FILES."
        )

    @pytest.mark.parametrize("module", FEATURE_MODULES)
    def test_every_endpoint_is_reachable_on_the_app(self, module: str):
        # Asked of the built app rather than read off api/v1/__init__.py, so a router that is
        # imported but never included - or included under a typo'd prefix - fails here too.
        for function in functions_in(module_source(module, "routes.py")):
            if not any(is_call_to(decorator, verb) for decorator in function.decorator_list for verb in HTTP_VERBS):
                continue

            served = mounted_paths_of(function.name)

            assert served, (
                f"modules/{module}/routes.py: {function.name} is decorated as an endpoint but serves "
                f"no URL on the app. Its router is never included in interfaces/api/v1/__init__.py."
            )
            assert all(path.startswith(f"{API_PREFIX}/") for path in served), (
                f"modules/{module}/routes.py: {function.name} is mounted at {served}, outside "
                f"{API_PREFIX}/. Prefixes are set at registration in api/v1/__init__.py."
            )

    @pytest.mark.parametrize("module", FEATURE_MODULES)
    def test_every_submodule_imports_cleanly(self, module: str):
        # migrations/env.py discovers models by walking src.modules with `except ImportError: pass`,
        # so anything that fails to import is silently absent from
        # `alembic revision --autogenerate`. Walk the same way it does rather than importing
        # models.py alone: a broken sibling takes the whole package's models down with it.
        package = importlib.import_module(f"src.modules.{module}")

        for _, submodule, _ in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
            importlib.import_module(submodule)


class TestDataclassModelRules:
    """`init=False` and `lazy="selectin"` are the two rules whose absence crashes at runtime."""

    @pytest.mark.parametrize("module", FEATURE_MODULES)
    def test_primary_keys_are_excluded_from_init(self, module: str):
        source = module_source(module, "models.py")
        offenders = [
            call.lineno
            for call in calls_named(source, "mapped_column")
            if keyword_of(call, "primary_key") is not None and keyword_of(call, "init") is None
        ]

        assert not offenders, (
            f"modules/{module}/models.py has a primary key without init=False at lines {offenders}. "
            f"These are dataclass models - the __init__ conflict crashes on insert."
        )

    @pytest.mark.parametrize("module", FEATURE_MODULES)
    def test_relationships_are_selectin_and_excluded_from_init(self, module: str):
        source = module_source(module, "models.py")

        for call in calls_named(source, "relationship"):
            lazy = keyword_of(call, "lazy")
            assert keyword_of(call, "init") is not None, (
                f"modules/{module}/models.py line {call.lineno}: relationship without init=False crashes on insert."
            )
            assert isinstance(lazy, ast.Constant), (
                f'modules/{module}/models.py line {call.lineno}: relationship needs a literal lazy="selectin".'
            )
            assert lazy.value == "selectin", (
                f'modules/{module}/models.py line {call.lineno}: relationship needs lazy="selectin" '
                f"- anything else lazy-loads on attribute access, which raises MissingGreenlet under async sessions."
            )
            assert keyword_of(call, "default") is None, (
                f"modules/{module}/models.py line {call.lineno}: relationship(default=...) makes "
                f"SQLAlchemy clear the foreign key on commit. Use default_factory or nothing."
            )

    @pytest.mark.parametrize("module", FEATURE_MODULES)
    def test_foreign_keys_are_indexed(self, module: str):
        source = module_source(module, "models.py")
        offenders = [
            call.lineno
            for call in calls_named(source, "mapped_column")
            if any(
                isinstance(argument, ast.Call) and getattr(argument.func, "id", None) == "ForeignKey" for argument in call.args
            )
            and keyword_of(call, "index") is None
        ]

        assert not offenders, f"modules/{module}/models.py has an unindexed foreign key at lines {offenders}."


# The boilerplate's auth layer is built on the user model and the shared error handler; nothing else
# under `infrastructure` may reach up into a feature module.
INFRASTRUCTURE_MODULE_IMPORTS_ALLOWED = {"user", "common"}


def imported_modules_of(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.ImportFrom) and node.module:
            dotted = node.module.split(".")
            if "modules" in dotted and (node.level > 0 or dotted[0] == "src"):
                names.add(dotted[dotted.index("modules") + 1] if len(dotted) > dotted.index("modules") + 1 else "")
    return names


class TestDependencyDirection:
    def test_infrastructure_imports_no_feature_module(self):
        offenders = {
            str(path.relative_to(BACKEND_DIRECTORY)): sorted(imported - INFRASTRUCTURE_MODULE_IMPORTS_ALLOWED)
            for path in (BACKEND_DIRECTORY / "src" / "infrastructure").rglob("*.py")
            if (imported := imported_modules_of(path)) - INFRASTRUCTURE_MODULE_IMPORTS_ALLOWED
        }
        assert offenders == {}

    def test_modules_never_import_interfaces(self):
        offenders = [
            str(path.relative_to(BACKEND_DIRECTORY))
            for path in MODULES_DIRECTORY.rglob("*.py")
            for node in ast.walk(parse(path))
            if isinstance(node, ast.ImportFrom) and node.module and "interfaces" in node.module.split(".")
        ]
        assert offenders == []
