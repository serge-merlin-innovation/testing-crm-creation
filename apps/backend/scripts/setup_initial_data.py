import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from scripts.create_first_admin import create_first_admin  # noqa: E402
from src.infrastructure.database.session import create_tables  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402

logger = get_logger()


async def setup_initial_data() -> None:
    logger.info("Setting up initial data...")

    logger.info("Creating database tables...")
    try:
        await create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}", exc_info=True)
        sys.exit(1)

    logger.info("Seeding roles and the first Admin...")
    await create_first_admin()

    logger.info("Initial data setup complete")


if __name__ == "__main__":
    asyncio.run(setup_initial_data())
