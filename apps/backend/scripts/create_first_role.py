import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import select  # noqa: E402

from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.role.models import Role  # noqa: E402

logger = get_logger()


async def create_first_role() -> None:
    try:
        role_name = getattr(settings, "DEFAULT_ROLE_NAME", "member")

        async with local_session() as session:
            query = select(Role).where(Role.name == role_name)
            result = await session.execute(query)
            role = result.scalar_one_or_none()

            if role:
                logger.info(f"Role '{role_name}' already exists with ID {role.id}")
                return

            role = Role(name=role_name)
            session.add(role)
            await session.commit()
            await session.refresh(role)

            logger.info(f"Role '{role_name}' created successfully with ID {role.id}")

    except Exception as e:
        logger.error(f"Error creating role: {e}")


async def main() -> None:
    await create_first_role()


if __name__ == "__main__":
    asyncio.run(main())
