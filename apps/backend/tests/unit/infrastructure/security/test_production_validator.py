from unittest.mock import Mock

import pytest

from src.infrastructure.config.settings import EnvironmentOption, Settings
from src.infrastructure.security.production_validator import (
    ProductionSecurityError,
    ProductionSecurityValidator,
    validate_production_security,
)


class TestProductionSecurityValidator:
    def create_mock_settings(self, **overrides):
        defaults = {
            "ENVIRONMENT": EnvironmentOption.PRODUCTION,
            "SECRET_KEY": "xF9mWqP3nL7vBfKsRt8HjZ2CyE5QaM6NuV4DgX1SpY7LwB9KzT3RhI0UoJ5PcA2MvS8",
            "POSTGRES_PASSWORD": "secure_db_password",
            "CORS_ENABLED": True,
            "CORS_ORIGINS": "https://example.com",
            "DEBUG": False,
            "ENABLE_DOCS_IN_PRODUCTION": False,
            "SESSION_SECURE_COOKIES": True,
            "SESSION_TIMEOUT_MINUTES": 30,
            "CSRF_ENABLED": True,
            "FIRST_SUPERUSER_USERNAME": "secure_admin_user",
            "FIRST_SUPERUSER_PASSWORD": "very_secure_admin_password_123",
            "PRODUCTION_SECURITY_VALIDATION_ENABLED": True,
            "PRODUCTION_SECURITY_STRICT_MODE": False,
            # OAuth settings - no Microsoft client configured by default, so the
            # tenant-scope check stays quiet unless a test opts in.
            "OAUTH_MICROSOFT_CLIENT_ID": "",
            "OAUTH_MICROSOFT_TENANT": "common",
        }
        defaults.update(overrides)

        settings = Mock(spec=Settings)
        for key, value in defaults.items():
            setattr(settings, key, value)

        def get_cors_origins_list():
            origins = getattr(settings, "CORS_ORIGINS", "*")
            if not origins:
                return ["*"]
            return [x.strip() for x in origins.split(",") if x.strip()]

        settings.CORS_ORIGINS_LIST = get_cors_origins_list()

        return settings

    def test_non_production_environment_skips_validation(self):
        settings = self.create_mock_settings(ENVIRONMENT=EnvironmentOption.DEVELOPMENT)
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

    def test_secure_production_config_passes(self):
        settings = self.create_mock_settings()
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

    def test_insecure_secret_key_raises_error(self):
        test_cases = [
            "insecure-secret-key-change-this",
            "change-me",
            "secret",
            "password",
            "123456",
            "short",  # Too short
            "",  # Empty
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",  # Repeated chars
            "abcd1234qwerty",  # Predictable patterns
        ]

        for insecure_key in test_cases:
            settings = self.create_mock_settings(SECRET_KEY=insecure_key)
            validator = ProductionSecurityValidator(settings)

            with pytest.raises(ProductionSecurityError) as exc_info:
                validator.validate_production_security()

            assert "SECRET_KEY" in str(exc_info.value)
            assert "insecure" in str(exc_info.value).lower()

    def test_default_database_password_raises_error(self):
        settings = self.create_mock_settings(POSTGRES_PASSWORD="postgres")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "Database" in str(exc_info.value)
        assert "default credentials" in str(exc_info.value)

    def test_empty_database_password_raises_error(self):
        settings = self.create_mock_settings(POSTGRES_PASSWORD="")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        assert "Database password is empty" in str(exc_info.value)

    def test_multiple_critical_errors_combined(self):
        settings = self.create_mock_settings(SECRET_KEY="insecure", POSTGRES_PASSWORD="postgres")
        validator = ProductionSecurityValidator(settings)

        with pytest.raises(ProductionSecurityError) as exc_info:
            validator.validate_production_security()

        error_msg = str(exc_info.value)
        assert "SECRET_KEY" in error_msg
        assert "Database" in error_msg

    def test_permissive_cors_logs_warning(self, caplog):
        settings = self.create_mock_settings(CORS_ORIGINS="*")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        cors_warnings = [log for log in warning_logs if "CORS_ORIGINS" in log.message and "allow all origins" in log.message]
        assert len(cors_warnings) > 0

    def test_debug_enabled_logs_warning(self, caplog):
        settings = self.create_mock_settings(DEBUG=True)
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        debug_warnings = [log for log in warning_logs if "DEBUG mode" in log.message]
        assert len(debug_warnings) > 0

    def test_docs_enabled_logs_warning(self, caplog):
        settings = self.create_mock_settings(ENABLE_DOCS_IN_PRODUCTION=True)
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        docs_warnings = [log for log in warning_logs if "API documentation" in log.message]
        assert len(docs_warnings) > 0

    def test_multi_tenant_microsoft_oauth_logs_warning(self, caplog):
        settings = self.create_mock_settings(
            OAUTH_MICROSOFT_CLIENT_ID="a-client-id",
            OAUTH_MICROSOFT_TENANT="common",
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        tenant_warnings = [log for log in warning_logs if "OAUTH_MICROSOFT_TENANT" in log.message]
        assert len(tenant_warnings) > 0

    def test_single_tenant_microsoft_oauth_logs_no_warning(self, caplog):
        settings = self.create_mock_settings(
            OAUTH_MICROSOFT_CLIENT_ID="a-client-id",
            OAUTH_MICROSOFT_TENANT="11111111-2222-3333-4444-555555555555",
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        tenant_warnings = [log for log in warning_logs if "OAUTH_MICROSOFT_TENANT" in log.message]
        assert len(tenant_warnings) == 0

    def test_unconfigured_microsoft_oauth_logs_no_warning(self, caplog):
        settings = self.create_mock_settings(OAUTH_MICROSOFT_CLIENT_ID="", OAUTH_MICROSOFT_TENANT="common")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        tenant_warnings = [log for log in warning_logs if "OAUTH_MICROSOFT_TENANT" in log.message]
        assert len(tenant_warnings) == 0

    def test_insecure_session_config_logs_warning(self, caplog):
        settings = self.create_mock_settings(
            SESSION_SECURE_COOKIES=False,
            SESSION_TIMEOUT_MINUTES=180,  # 3 hours
            CSRF_ENABLED=False,
        )
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]

        cookie_warnings = [log for log in warning_logs if "SESSION_SECURE_COOKIES" in log.message]
        timeout_warnings = [log for log in warning_logs if "Session timeout" in log.message]
        csrf_warnings = [log for log in warning_logs if "CSRF protection" in log.message]

        assert len(cookie_warnings) > 0
        assert len(timeout_warnings) > 0
        assert len(csrf_warnings) > 0

    def test_weak_first_superuser_credentials_logs_warning(self, caplog):
        settings = self.create_mock_settings(FIRST_SUPERUSER_USERNAME="admin", FIRST_SUPERUSER_PASSWORD="123456")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]

        username_warnings = [
            log for log in warning_logs if "First superuser username" in log.message and "predictable" in log.message
        ]
        password_warnings = [log for log in warning_logs if "First superuser password" in log.message]

        assert len(username_warnings) > 0
        assert len(password_warnings) > 0

    def test_convenience_function(self):
        settings = self.create_mock_settings(SECRET_KEY="insecure")

        with pytest.raises(ProductionSecurityError):
            validate_production_security(settings)

    def test_no_first_superuser_credentials_skips_credential_checks(self, caplog):
        settings = self.create_mock_settings(FIRST_SUPERUSER_USERNAME="", FIRST_SUPERUSER_PASSWORD="")
        validator = ProductionSecurityValidator(settings)

        validator.validate_production_security()

        warning_logs = [record for record in caplog.records if record.levelname == "WARNING"]
        credential_warnings = [log for log in warning_logs if "First superuser" in log.message]
        assert len(credential_warnings) == 0
