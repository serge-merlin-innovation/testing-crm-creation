import pytest

from src.infrastructure.database.migration_validation import validate_production_migration


def test_non_production_migration_does_not_require_confirmation() -> None:
    validate_production_migration({"ENVIRONMENT": "development"})


def test_production_migration_requires_explicit_confirmation() -> None:
    with pytest.raises(RuntimeError, match="CONFIRM_PRODUCTION_MIGRATION=yes"):
        validate_production_migration({"ENVIRONMENT": "production"})


def test_production_migration_accepts_database_url() -> None:
    validate_production_migration(
        {
            "ENVIRONMENT": "production",
            "CONFIRM_PRODUCTION_MIGRATION": "yes",
            "DATABASE_URL": "postgresql+asyncpg://user:password@database.example/db",
            "SECRET_KEY": "production-secret",
        }
    )


def test_production_migration_accepts_postgres_components() -> None:
    validate_production_migration(
        {
            "ENVIRONMENT": "production",
            "CONFIRM_PRODUCTION_MIGRATION": "yes",
            "POSTGRES_USER": "app",
            "POSTGRES_PASSWORD": "password",
            "POSTGRES_SERVER": "database.example",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "app",
            "SECRET_KEY": "production-secret",
        }
    )


def test_production_migration_rejects_incomplete_postgres_components() -> None:
    with pytest.raises(RuntimeError, match="POSTGRES_SERVER"):
        validate_production_migration(
            {
                "ENVIRONMENT": "production",
                "CONFIRM_PRODUCTION_MIGRATION": "yes",
                "POSTGRES_USER": "app",
                "POSTGRES_PASSWORD": "password",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "app",
                "SECRET_KEY": "production-secret",
            }
        )


def test_production_migration_requires_secret_key() -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_migration(
            {
                "ENVIRONMENT": "production",
                "CONFIRM_PRODUCTION_MIGRATION": "yes",
                "DATABASE_URL": "postgresql+asyncpg://user:password@database.example/db",
            }
        )
