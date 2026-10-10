import re

from ..config.settings import EnvironmentOption, Settings
from ..logging import get_logger

logger = get_logger()


class ProductionSecurityError(Exception):
    pass


class ProductionSecurityValidator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger()

    def validate_production_security(self) -> None:
        if not self._is_production():
            self.logger.debug("Not in production environment, skipping security validation")
            return

        self.logger.info("Running production security validation...")

        critical_errors = self._validate_critical_security()
        if critical_errors:
            error_msg = "Critical security issues detected in production:\n" + "\n".join(
                f"  • {error}" for error in critical_errors
            )
            self.logger.error(error_msg)
            raise ProductionSecurityError(error_msg)

        self._validate_warning_security()

        self.logger.info("Production security validation completed successfully")

    def _is_production(self) -> bool:
        return self.settings.ENVIRONMENT == EnvironmentOption.PRODUCTION

    def _validate_critical_security(self) -> list[str]:
        errors = []

        if self._is_insecure_secret_key():
            errors.append(
                "SECRET_KEY is using default or insecure value. "
                "This compromises session security, CSRF protection, and JWT tokens. "
                "Generate a strong, unique secret key for production."
            )

        if self._is_database_using_default_credentials():
            errors.append(
                "Database is using default credentials (POSTGRES_PASSWORD='postgres'). "
                "This is a well-known default that attackers will try first. "
                "Use a strong, unique password for production."
            )

        if self._is_database_password_empty():
            errors.append(
                "Database password is empty (POSTGRES_PASSWORD is not set). "
                "This leaves your database completely unprotected. "
                "Set a strong password for production."
            )

        return errors

    def _validate_warning_security(self) -> None:
        warnings = []

        if self._is_cors_too_permissive():
            warnings.append(
                "CORS_ORIGINS is set to '*' (allow all origins). This can enable "
                "cross-origin attacks. Consider restricting to specific domains in production."
            )

        if self._is_debug_enabled():
            warnings.append(
                "DEBUG mode is enabled in production. This can expose sensitive information "
                "in error responses and enable debug endpoints. Set DEBUG=false for production."
            )

        docs_warning = self._check_docs_security()
        if docs_warning:
            warnings.append(docs_warning)

        session_warnings = self._check_session_security()
        warnings.extend(session_warnings)

        warnings.extend(self._check_first_admin_credentials())

        for warning in warnings:
            self.logger.warning(f"PRODUCTION SECURITY WARNING: {warning}")

        if warnings:
            self.logger.warning(
                f"Found {len(warnings)} production security warnings. "
                "While not critical, these should be reviewed for optimal security."
            )

    def _is_insecure_secret_key(self) -> bool:
        secret = self.settings.SECRET_KEY

        if not secret:
            return True

        insecure_patterns = [
            "insecure-secret-key-change-this",
            "change-me",
            "change-this",
            "default",
            "secret",
            "password",
            "secretkey",
            "key",
            "123456",
            "abc123",
            "test",
            "dev",
            "development",
        ]

        secret_lower = secret.lower()
        if any(pattern in secret_lower for pattern in insecure_patterns):
            return True

        if len(secret) < 32:
            return True

        if self._has_predictable_pattern(secret):
            return True

        return False

    def _has_predictable_pattern(self, secret: str) -> bool:
        if re.search(r"(.)\1{3,}", secret):
            return True

        if "1234" in secret or "abcd" in secret.lower() or "qwerty" in secret.lower():
            return True

        return False

    def _is_database_using_default_credentials(self) -> bool:
        return self.settings.POSTGRES_PASSWORD == "postgres"

    def _is_database_password_empty(self) -> bool:
        return not self.settings.POSTGRES_PASSWORD or self.settings.POSTGRES_PASSWORD.strip() == ""

    def _is_cors_too_permissive(self) -> bool:
        return self.settings.CORS_ENABLED and "*" in self.settings.CORS_ORIGINS_LIST

    def _is_debug_enabled(self) -> bool:
        return self.settings.DEBUG

    def _check_docs_security(self) -> str:
        if self.settings.ENABLE_DOCS_IN_PRODUCTION:
            return (
                "API documentation is enabled in production (ENABLE_DOCS_IN_PRODUCTION=true). "
                "This exposes your API schema and endpoints publicly. Ensure proper access "
                "controls are in place or disable docs in production."
            )
        return ""

    def _check_session_security(self) -> list[str]:
        warnings: list[str] = []

        if not self.settings.SESSION_SECURE_COOKIES:
            warnings.append(
                "SESSION_SECURE_COOKIES is disabled. This allows session cookies to be "
                "transmitted over unencrypted HTTP connections, making them vulnerable "
                "to interception. Enable secure cookies in production."
            )

        if self.settings.SESSION_TIMEOUT_MINUTES > 120:
            warnings.append(
                f"Session timeout is set to {self.settings.SESSION_TIMEOUT_MINUTES} minutes "
                f"(more than 2 hours). Long session timeouts increase security risk if "
                f"a session is compromised. Consider reducing the timeout for production."
            )

        if not self.settings.CSRF_ENABLED:
            warnings.append(
                "CSRF protection is disabled. This makes your application vulnerable to "
                "Cross-Site Request Forgery attacks. Enable CSRF protection in production."
            )

        return warnings

    def _check_first_admin_credentials(self) -> list[str]:
        warnings: list[str] = []

        if not self.settings.FIRST_ADMIN_EMAIL or not self.settings.FIRST_ADMIN_PASSWORD:
            return warnings

        password = self.settings.FIRST_ADMIN_PASSWORD
        if len(password) < 12:
            warnings.append(
                "First admin password is shorter than 12 characters. Use a longer, "
                "stronger password for the first admin in production."
            )

        weak_passwords = {
            "password",
            "123456",
            "admin",
            "password123",
            "admin123",
            "qwerty",
            "letmein",
            "welcome",
            "changeme",
            "123456",
            "12345678",
            "1234",
            "123",
            "12345",
            "123456789",
            "adminisp",
            "demo",
            "root",
            "123123",
            "admin@123",
            "123456aA@",
            "01031974",
            "Admin@123",
            "111111",
            "admin1234",
            "admin1",
        }
        if password.lower() in weak_passwords:
            warnings.append(
                "First admin password appears to be a common weak password. Use a strong, unique password for the first admin."
            )

        return warnings


def validate_production_security(settings: Settings) -> None:
    validator = ProductionSecurityValidator(settings)
    validator.validate_production_security()
