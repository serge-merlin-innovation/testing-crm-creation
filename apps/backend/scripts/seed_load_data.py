"""Seeds a throwaway database for the NFR-02 load test: N contacts (default 200,000) and API tokens.

Refuses to run against anything but a database on this machine or a CI service container, and never
when ENVIRONMENT is staging or production. Prints one API token per virtual user, comma-separated,
on the last line for k6: each token has its own 100-per-minute bucket, so the run measures latency.

    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55611/crm \\
      uv run python -m scripts.seed_load_data --contacts 200000
"""

import argparse
import asyncio
import hashlib
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from sqlalchemy import func, insert, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from src.infrastructure.config.settings import EnvironmentOption, settings  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.modules.api_access.models import ApiToken  # noqa: E402
from src.modules.contact.models import Contact  # noqa: E402
from src.modules.role.models import Role  # noqa: E402
from src.modules.role.permissions import RoleName  # noqa: E402
from src.modules.user.models import User  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}
BATCH = 5000
FIRST_NAMES = ["Anna", "Bart", "Chloé", "Dirk", "Eva", "Filip", "Greet", "Hugo", "Ines", "Jan", "Karel", "Lotte"]
LAST_NAMES = ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes", "Goossens", "Wouters", "Dubois"]


def refuse_unless_throwaway() -> None:
    host = urlsplit(settings.DATABASE_URL.replace("+asyncpg", "")).hostname or ""
    if settings.ENVIRONMENT in (EnvironmentOption.PRODUCTION, EnvironmentOption.STAGING) or host not in LOCAL_HOSTS:
        sys.exit(f"Refusing to seed load data into {host or 'an unknown host'} ({settings.ENVIRONMENT}).")


LOAD_USER = "load.partner@example.test"


async def load_partner(db: AsyncSession) -> int:
    """A Partner, so the token reaches records and the firm-wide reports like a real fee earner."""
    user_id: int | None = (await db.execute(select(User.id).where(User.email == LOAD_USER))).scalar_one_or_none()
    if user_id is None:
        role_id = (await db.execute(select(Role.id).where(Role.name == RoleName.PARTNER.value))).scalar_one()
        user = User(name="Load Partner", email=LOAD_USER, hashed_password="!", role_id=role_id)
        db.add(user)
        await db.flush()
        user_id = user.id
    return user_id


async def seed(contacts: int, tokens: int) -> str:
    async with local_session() as db:
        owner_id = await load_partner(db)
        existing = (await db.execute(select(func.count(Contact.id)))).scalar_one()
        now = datetime.now(UTC)
        for start in range(existing, contacts, BATCH):
            rows = [
                {
                    "first_name": FIRST_NAMES[index % len(FIRST_NAMES)],
                    "last_name": f"{LAST_NAMES[index % len(LAST_NAMES)]}{index}",
                    "email": f"load{index}@example.test",
                    "source": "load test",
                    "owner_id": owner_id,
                    "created_at": now,
                }
                for index in range(start, min(start + BATCH, contacts))
            ]
            await db.execute(insert(Contact), rows)
            await db.commit()
        issued = []
        for _ in range(tokens):
            secret = "crm_pat_" + secrets.token_urlsafe(32)
            db.add(
                ApiToken(
                    user_id=owner_id,
                    kind="personal",
                    name="k6 load test",
                    prefix=secret[:12],
                    token_hash=hashlib.sha256(secret.encode()).hexdigest(),
                    created_at=now,
                )
            )
            issued.append(secret)
        await db.commit()
        return ",".join(issued)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contacts", type=int, default=200_000)
    parser.add_argument("--tokens", type=int, default=50)
    arguments = parser.parse_args()
    refuse_unless_throwaway()
    sys.stdout.write(asyncio.run(seed(arguments.contacts, arguments.tokens)) + "\n")


if __name__ == "__main__":
    main()
