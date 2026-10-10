"""Seeds the NFR-02 load-test dataset into DATABASE_URL and writes the bearer tokens k6 uses.

Usage: uv run python -m scripts.seed_load_test  (after alembic upgrade head and setup_initial_data).
Never run against production: it adds 200,000 synthetic contacts.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from scripts.load_dataset import ROLE_MIX, seed_load_dataset  # noqa: E402
from src.infrastructure.config.settings import EnvironmentOption, settings  # noqa: E402
from src.infrastructure.database.session import local_session  # noqa: E402
from src.modules.picklist.service import seed_default_picklists  # noqa: E402

TOKENS_FILE = Path(__file__).resolve().parent.parent / "perf" / "k6" / "tokens.json"


async def main() -> None:
    if settings.ENVIRONMENT == EnvironmentOption.PRODUCTION:
        raise SystemExit("Refusing to seed load-test data into production.")
    async with local_session() as db:
        await seed_default_picklists(db)
        dataset = await seed_load_dataset(db)
    roles = {uid: ROLE_MIX[index % len(ROLE_MIX)] for index, uid in enumerate(dataset.user_ids)}
    # Read-only users see the aggregated dashboards only (ticket #17), so k6 sends them there.
    users = [{"token": token, "dashboards_only": roles[uid] == "Read-only"} for uid, token in dataset.tokens.items()]
    TOKENS_FILE.write_text(json.dumps(users))
    print(  # noqa: T201
        f"Seeded {len(dataset.user_ids)} users, {dataset.contacts} contacts, "
        f"{dataset.companies} companies, {dataset.deals} deals"
    )
    print(f"Wrote {len(dataset.tokens)} tokens to {TOKENS_FILE}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
