import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from crudauth import get_password_hash  # noqa: E402
from sqlalchemy import select  # noqa: E402

from src.infrastructure.config.settings import settings  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.infrastructure.logging import get_logger  # noqa: E402
from src.modules.role.models import Role  # noqa: E402
from src.modules.role.permissions import RoleName  # noqa: E402
from src.modules.role.service import seed_default_roles  # noqa: E402
from src.modules.user.models import User  # noqa: E402

logger = get_logger()


async def create_first_admin() -> None:
    name = settings.FIRST_ADMIN_NAME or "Admin User"
    email = settings.FIRST_ADMIN_EMAIL or "admin@example.com"
    password = settings.FIRST_ADMIN_PASSWORD or "admin123"

    async with local_session() as session:
        await seed_default_roles(session)
        admin_role_id = (await session.execute(select(Role.id).where(Role.name == RoleName.ADMIN.value))).scalar_one()
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            session.add(User(name=name, email=email, hashed_password=get_password_hash(password), role_id=admin_role_id))
            logger.info(f"Admin {email} created")
        elif user.role_id != admin_role_id:
            user.role_id = admin_role_id
            logger.info(f"Existing user {email} given the Admin role")
        await session.commit()


async def main() -> None:
    await create_first_admin()


if __name__ == "__main__":
    asyncio.run(main())
