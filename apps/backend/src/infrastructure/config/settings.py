import logging
import os
from enum import StrEnum

from pydantic_settings import BaseSettings
from starlette.config import Config

from .enums import LogFormat, LogLevel

logger = logging.getLogger(__name__)

current_file_dir = os.path.dirname(os.path.realpath(__file__))
project_root = os.path.abspath(os.path.join(current_file_dir, "..", "..", ".."))

env_paths = [
    "/app/.env",
    os.path.join(project_root, ".env"),
    "/.env",
]

env_path = next((path for path in env_paths if os.path.isfile(path)), env_paths[0])
logger.info(f"Using environment file at: {env_path}")

config = Config(env_path)


class EnvironmentOption(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    LOCAL = "local"


class EnvironmentSettings(BaseSettings):
    ENVIRONMENT: EnvironmentOption = config("ENVIRONMENT", default=EnvironmentOption.DEVELOPMENT, cast=EnvironmentOption)


class DatabaseSettings(BaseSettings):
    POSTGRES_USER: str = config("POSTGRES_USER", default="postgres")
    POSTGRES_PASSWORD: str = config("POSTGRES_PASSWORD", default="postgres")
    POSTGRES_SERVER: str = config("POSTGRES_SERVER", default="localhost")
    POSTGRES_PORT: int = config("POSTGRES_PORT", default=5432)
    POSTGRES_DB: str = config("POSTGRES_DB", default="postgres")
    POSTGRES_SYNC_PREFIX: str = config("POSTGRES_SYNC_PREFIX", default="postgresql://")
    POSTGRES_ASYNC_PREFIX: str = config("POSTGRES_ASYNC_PREFIX", default="postgresql+asyncpg://")
    CREATE_TABLES_ON_STARTUP: bool = config("CREATE_TABLES_ON_STARTUP", default=True, cast=bool)

    POSTGRES_POOL_SIZE: int = config("POSTGRES_POOL_SIZE", default=20, cast=int)
    POSTGRES_MAX_OVERFLOW: int = config("POSTGRES_MAX_OVERFLOW", default=0, cast=int)

    @property
    def DATABASE_URL(self) -> str:
        direct_url = config("DATABASE_URL", default=None)
        if direct_url:
            return direct_url

        return (
            f"{self.POSTGRES_ASYNC_PREFIX}{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


class CORSSettings(BaseSettings):
    CORS_ENABLED: bool = config("CORS_ENABLED", default=True, cast=bool)
    CORS_ORIGINS: str = config("CORS_ORIGINS", default="*")
    CORS_ALLOW_CREDENTIALS: bool = config("CORS_ALLOW_CREDENTIALS", default=True, cast=bool)

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return ["*"]
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

    CORS_ALLOW_METHODS: str = config("CORS_ALLOW_METHODS", default="*")
    CORS_ALLOW_HEADERS: str = config("CORS_ALLOW_HEADERS", default="*")


class CompressionSettings(BaseSettings):
    GZIP_ENABLED: bool = config("GZIP_ENABLED", default=True, cast=bool)
    GZIP_MINIMUM_SIZE: int = config("GZIP_MINIMUM_SIZE", default=1000, cast=int)


class APIDocSettings(BaseSettings):
    ENABLE_DOCS_IN_PRODUCTION: bool = config("ENABLE_DOCS_IN_PRODUCTION", default=False, cast=bool)
    OPENAPI_PREFIX: str = config("OPENAPI_PREFIX", default="")
    DOCS_URL: str = config("DOCS_URL", default="/docs")
    REDOC_URL: str = config("REDOC_URL", default="/redoc")
    OPENAPI_URL: str = config("OPENAPI_URL", default="/openapi.json")

    API_TITLE: str = config("API_TITLE", default="")
    API_SUMMARY: str = config("API_SUMMARY", default="")
    API_DESCRIPTION: str = config("API_DESCRIPTION", default="")
    API_VERSION: str = config("API_VERSION", default="")
    API_TERMS_OF_SERVICE: str = config("API_TERMS_OF_SERVICE", default="")

    API_CONTACT_NAME: str = config("API_CONTACT_NAME", default="")
    API_CONTACT_URL: str = config("API_CONTACT_URL", default="")
    API_CONTACT_EMAIL: str = config("API_CONTACT_EMAIL", default="")

    API_LICENSE_NAME: str = config("API_LICENSE_NAME", default="")
    API_LICENSE_URL: str = config("API_LICENSE_URL", default="")
    API_LICENSE_IDENTIFIER: str = config("API_LICENSE_IDENTIFIER", default="")

    API_TAGS_METADATA: str = config("API_TAGS_METADATA", default="[]")


class AuthSettings(BaseSettings):
    SECRET_KEY: str = config("SECRET_KEY", default="insecure-secret-key-change-this")

    SESSION_TIMEOUT_MINUTES: int = config("SESSION_TIMEOUT_MINUTES", default=30, cast=int)
    SESSION_CLEANUP_INTERVAL_MINUTES: int = config("SESSION_CLEANUP_INTERVAL_MINUTES", default=15, cast=int)
    MAX_SESSIONS_PER_USER: int = config("MAX_SESSIONS_PER_USER", default=5, cast=int)
    SESSION_SECURE_COOKIES: bool = config("SESSION_SECURE_COOKIES", default=True, cast=bool)

    CSRF_ENABLED: bool = config("CSRF_ENABLED", default=True, cast=bool)

    # Number of trusted reverse proxies in front of the app. crudauth resolves the
    # client IP for login lockout from the last hop of X-Forwarded-For; 0 = the socket
    # peer (no proxy). Set to 1 behind a single nginx/Caddy, 2 if Cloudflare is also in front.
    TRUSTED_PROXY_HOPS: int = config("TRUSTED_PROXY_HOPS", default=0, cast=int)

    # Scheduled-job runner (reminders, expiries, digests, retention). Off in tests, which use the
    # test-only "run jobs now" hook instead.
    SCHEDULED_JOBS_ENABLED: bool = config("SCHEDULED_JOBS_ENABLED", default=True, cast=bool)
    SCHEDULED_JOBS_TICK_SECONDS: int = config("SCHEDULED_JOBS_TICK_SECONDS", default=60, cast=int)


class APISettings(BaseSettings):
    API_PREFIX: str = "/api"


class AppSettings(BaseSettings):
    APP_NAME: str = config("APP_NAME", default="FastAPI Boilerplate")
    APP_DESCRIPTION: str = config("APP_DESCRIPTION", default="Modular FastAPI starter")
    DEBUG: bool = config("DEBUG", default=False, cast=bool)
    VERSION: str = config("VERSION", default="0.1.0")
    CONTACT_NAME: str = config("CONTACT_NAME", default="Support")
    CONTACT_EMAIL: str = config("CONTACT_EMAIL", default="support@example.com")
    LICENSE_NAME: str = config("LICENSE_NAME", default="All rights reserved.")
    APP_URL: str = config("APP_URL", default="http://localhost:3000")


class FirstAdminSettings(BaseSettings):
    FIRST_ADMIN_NAME: str = config("FIRST_ADMIN_NAME", default="")
    FIRST_ADMIN_EMAIL: str = config("FIRST_ADMIN_EMAIL", default="")
    FIRST_ADMIN_PASSWORD: str = config("FIRST_ADMIN_PASSWORD", default="")


class SecuritySettings(BaseSettings):
    PRODUCTION_SECURITY_VALIDATION_ENABLED: bool = config("PRODUCTION_SECURITY_VALIDATION_ENABLED", default=True, cast=bool)
    PRODUCTION_SECURITY_STRICT_MODE: bool = config("PRODUCTION_SECURITY_STRICT_MODE", default=False, cast=bool)
    SECURITY_HEADERS_ENABLED: bool = config("SECURITY_HEADERS_ENABLED", default=True, cast=bool)


class LoggingSettings(BaseSettings):
    LOG_LEVEL: str = config("LOG_LEVEL", default=LogLevel.INFO.value)
    LOG_FORMAT: str = config("LOG_FORMAT", default=LogFormat.STRUCTURED.value)

    LOG_CONSOLE_ENABLED: bool = config("LOG_CONSOLE_ENABLED", default=True, cast=bool)
    LOG_FILE_ENABLED: bool = config("LOG_FILE_ENABLED", default=False, cast=bool)
    LOG_FILE_PATH: str = config("LOG_FILE_PATH", default="logs/app.log")
    LOG_FILE_MAX_SIZE: int = config("LOG_FILE_MAX_SIZE", default=10485760, cast=int)
    LOG_FILE_BACKUP_COUNT: int = config("LOG_FILE_BACKUP_COUNT", default=5, cast=int)

    LOG_CORRELATION_ID: bool = config("LOG_CORRELATION_ID", default=True, cast=bool)
    LOG_STRUCTURED_CONTEXT: bool = config("LOG_STRUCTURED_CONTEXT", default=True, cast=bool)
    LOG_PERFORMANCE_METRICS: bool = config("LOG_PERFORMANCE_METRICS", default=False, cast=bool)

    LOG_SQL_QUERIES: bool = config("LOG_SQL_QUERIES", default=False, cast=bool)
    LOG_INCLUDE_STACKTRACE: bool = config("LOG_INCLUDE_STACKTRACE", default=True, cast=bool)

    LOG_DEVELOPMENT_VERBOSE: bool = config("LOG_DEVELOPMENT_VERBOSE", default=True, cast=bool)
    LOG_PRODUCTION_OPTIMIZE: bool = config("LOG_PRODUCTION_OPTIMIZE", default=True, cast=bool)

    @property
    def LOG_LEVEL_INT(self) -> int:
        level_map = {
            LogLevel.DEBUG.value: logging.DEBUG,
            LogLevel.INFO.value: logging.INFO,
            LogLevel.WARNING.value: logging.WARNING,
            LogLevel.ERROR.value: logging.ERROR,
            LogLevel.CRITICAL.value: logging.CRITICAL,
        }
        return level_map.get(self.LOG_LEVEL.upper(), logging.INFO)


class Settings(
    EnvironmentSettings,
    DatabaseSettings,
    CORSSettings,
    CompressionSettings,
    APIDocSettings,
    AuthSettings,
    APISettings,
    AppSettings,
    FirstAdminSettings,
    SecuritySettings,
    LoggingSettings,
):
    pass


settings = Settings()


def get_settings() -> Settings:
    return settings
