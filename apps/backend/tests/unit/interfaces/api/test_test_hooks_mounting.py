import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.infrastructure.config.settings import EnvironmentOption
from src.infrastructure.security.production_validator import ProductionSecurityError, ProductionSecurityValidator

BACKEND_DIRECTORY = Path(__file__).parents[4]

PROBE = (
    "from src.interfaces.main import app\n"
    "from src.modules.mandate.policy import served_routes\n"
    "print(any(route.path.startswith('/api/v1/test-hooks') for route in served_routes(app.routes)))\n"
)


def probe(**overrides: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != "TEST_HOOKS_ENABLED"}
    environment.update({"ENVIRONMENT": "development", "PRODUCTION_SECURITY_VALIDATION_ENABLED": "false", **overrides})
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND_DIRECTORY, env=environment, capture_output=True, text=True, check=False
    )


def hooks_mounted(**overrides: str) -> bool:
    result = probe(**overrides)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1] == "True"


def test_hooks_are_off_unless_explicitly_enabled():
    assert not hooks_mounted()
    assert hooks_mounted(TEST_HOOKS_ENABLED="true")

    refused = probe(TEST_HOOKS_ENABLED="true", ENVIRONMENT="staging")
    assert refused.returncode != 0
    assert "TEST_HOOKS_ENABLED" in refused.stderr


@pytest.mark.parametrize("environment", [EnvironmentOption.PRODUCTION, EnvironmentOption.STAGING])
def test_validator_refuses_hooks_on_a_deployed_environment(environment):
    settings = type("S", (), {"ENVIRONMENT": environment, "TEST_HOOKS_ENABLED": True, "BREACH_CHECK_ENABLED": True})()
    with pytest.raises(ProductionSecurityError, match="TEST_HOOKS_ENABLED"):
        ProductionSecurityValidator(settings).validate_test_hooks()  # type: ignore[arg-type]


@pytest.mark.parametrize("environment", [EnvironmentOption.PRODUCTION, EnvironmentOption.STAGING])
def test_validator_refuses_a_disabled_breach_check_on_a_deployed_environment(environment):
    settings = type("S", (), {"ENVIRONMENT": environment, "TEST_HOOKS_ENABLED": False, "BREACH_CHECK_ENABLED": False})()
    with pytest.raises(ProductionSecurityError, match="BREACH_CHECK_ENABLED"):
        ProductionSecurityValidator(settings).validate_test_hooks()  # type: ignore[arg-type]
