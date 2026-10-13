import asyncio
import importlib
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src.infrastructure.config.settings import settings
from src.infrastructure.database.migration_validation import validate_production_migration
from src.infrastructure.database.session import Base
from src.modules.search.models import SEARCH_INDEXES

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# Run production safety checks
validate_production_migration()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def import_models(package_name):
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        try:
            importlib.import_module(module_name)
        except ImportError:
            # Skip modules that can't be imported (e.g., due to missing dependencies)
            pass


# Import all models to ensure they're registered with SQLAlchemy
import_models("src.modules")
target_metadata = Base.metadata

# Expression indexes created by raw DDL (see modules/search/models.py); autogenerate cannot model them.
RAW_DDL_INDEXES = {name for indexes in SEARCH_INDEXES.values() for name, _expression in indexes}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "index" and reflected and name in RAW_DDL_INDEXES)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
