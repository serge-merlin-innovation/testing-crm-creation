import os
from collections.abc import Mapping

POSTGRES_CONNECTION_VARIABLES = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_SERVER",
    "POSTGRES_PORT",
    "POSTGRES_DB",
)


def validate_production_migration(environment: Mapping[str, str] | None = None) -> None:
    values = os.environ if environment is None else environment

    if values.get("ENVIRONMENT") != "production":
        return

    if values.get("CONFIRM_PRODUCTION_MIGRATION") != "yes":
        raise RuntimeError(
            "Production migration requires CONFIRM_PRODUCTION_MIGRATION=yes. "
            "This confirms that the deployment may modify production data."
        )

    missing_requirements: list[str] = []
    if not values.get("DATABASE_URL"):
        missing_postgres_variables = [name for name in POSTGRES_CONNECTION_VARIABLES if not values.get(name)]
        if missing_postgres_variables:
            missing_requirements.append(
                f"DATABASE_URL or complete PostgreSQL settings (missing: {', '.join(missing_postgres_variables)})"
            )

    if not values.get("SECRET_KEY"):
        missing_requirements.append("SECRET_KEY")

    if missing_requirements:
        raise RuntimeError(f"Production migration configuration is incomplete: {'; '.join(missing_requirements)}")
