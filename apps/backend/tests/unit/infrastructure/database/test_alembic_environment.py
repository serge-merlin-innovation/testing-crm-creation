import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIRECTORY = Path(__file__).parents[4]


def test_offline_migration_accepts_percent_encoded_database_url() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "CONFIRM_PRODUCTION_MIGRATION": "yes",
            "DATABASE_URL": "postgresql+asyncpg://migration:p%40ss%25word@localhost:5432/app",
            "ENVIRONMENT": "production",
            "SECRET_KEY": "production-migration-test-secret",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head", "--sql"],
        cwd=BACKEND_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
