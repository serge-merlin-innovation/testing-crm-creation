import os
import re
from pathlib import Path
from unittest.mock import patch

from src.infrastructure.config.settings import Settings, get_settings

BACKEND_DIRECTORY = Path(__file__).parents[4]


class TestSettings:
    def test_settings_creation(self):
        settings = Settings()
        assert settings is not None
        assert hasattr(settings, "DATABASE_URL")
        assert hasattr(settings, "SECRET_KEY")

    def test_get_settings_singleton(self):
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    @patch.dict(os.environ, {"SECRET_KEY": "test_secret_key"})
    def test_settings_from_env(self):
        settings = Settings()
        assert settings.SECRET_KEY == "test_secret_key"

    def test_database_url_format(self):
        settings = get_settings()
        assert settings.DATABASE_URL is not None
        assert "://" in settings.DATABASE_URL

    @patch.dict(
        os.environ, {"DATABASE_URL": "postgresql+asyncpg://prod_user:prod_pass@prod.example.com:5432/prod_db"}, clear=False
    )
    def test_database_url_env_var_override(self):
        settings = Settings()
        expected_url = "postgresql+asyncpg://prod_user:prod_pass@prod.example.com:5432/prod_db"
        assert settings.DATABASE_URL == expected_url

    @patch.dict(os.environ, {}, clear=False)
    def test_database_url_fallback_to_constructed(self):
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        settings = Settings()
        assert "postgresql+asyncpg://" in settings.DATABASE_URL
        assert "postgres:postgres@localhost:5432" in settings.DATABASE_URL

    @patch.dict(os.environ, {"DEBUG": "true"})
    def test_debug_mode_setting(self):
        settings = Settings()
        if hasattr(settings, "DEBUG"):
            assert isinstance(settings.DEBUG, bool)

    def test_required_settings_exist(self):
        settings = get_settings()

        required_attrs = [
            "DATABASE_URL",
            "SECRET_KEY",
        ]

        for attr in required_attrs:
            assert hasattr(settings, attr), f"Missing required setting: {attr}"
            assert getattr(settings, attr) is not None, f"Setting {attr} is None"

    @patch.dict(os.environ, {"SQLITE_URI": ":memory:"})
    def test_test_database_override(self):
        settings = Settings()
        if hasattr(settings, "SQLITE_URI"):
            assert ":memory:" in settings.SQLITE_URI


class TestShippedEnvironmentExample:
    def test_env_example_does_not_disable_csrf(self):
        example = (BACKEND_DIRECTORY / ".env.example").read_text()

        assert "CSRF_ENABLED=false" not in example, (
            "`.env.example` is what every fork and every new developer starts from. Disabling CSRF "
            "there overrides the secure default in settings.py, and it is the only place in the "
            "repository that does."
        )

    def test_env_example_documents_every_configurable_setting(self):
        """A new setting goes in `settings.py` AND `.env.example`.

        A knob a fork cannot see in `.env.example` is a knob it does not know it has - the
        `API_*` group is this boilerplate's per-client rebrand surface.

        A commented line counts as documented: that is how an optional override with a good
        default is presented. The check runs both ways, so a key nothing reads is caught too -
        for that direction the fix is to stop reading it through `config()`, not to except it.
        """
        settings_source = (BACKEND_DIRECTORY / "src" / "infrastructure" / "config" / "settings.py").read_text()
        example = (BACKEND_DIRECTORY / ".env.example").read_text()

        read_from_environment = set(re.findall(r'config\(\s*"([A-Z0-9_]+)"', settings_source))
        documented = set(re.findall(r"^\s*#?\s*([A-Z0-9_]+)=", example, re.MULTILINE))

        assert not read_from_environment - documented, (
            f"{sorted(read_from_environment - documented)} are read from the environment in "
            f"settings.py but absent from .env.example."
        )
        assert not documented - read_from_environment, (
            f"{sorted(documented - read_from_environment)} appear in .env.example but are never "
            f"read through config(), so setting them does nothing."
        )
