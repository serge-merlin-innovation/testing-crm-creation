import os

# Configure the environment BEFORE importing anything from ``src``: settings and the
# crudauth ``auth`` singleton are built at import time and read these values.
# Tests run over http (base_url http://test), so the session/CSRF cookies must not be
# Secure-only or httpx won't send them back on follow-up requests.
os.environ.setdefault("SESSION_SECURE_COOKIES", "false")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("SQLITE_URI", ":memory:")
os.environ.setdefault("SQLITE_ASYNC_PREFIX", "sqlite+aiosqlite:///")
os.environ["CSRF_ENABLED"] = "true"
os.environ["CREATE_TABLES_ON_STARTUP"] = "false"
os.environ["SCHEDULED_JOBS_ENABLED"] = "false"

# Disable the testcontainers Ryuk reaper. Under `pytest -n auto`, each xdist worker
# is a separate process that spins up its own Ryuk container, and Docker Desktop
# chokes mapping all their ports at once ("Port mapping ... port 8080 is not
# available"). Testcontainers' own `with` blocks still clean up on normal exit.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from crudauth.ratelimit import MemoryRateLimiterBackend  # noqa: E402
from crudauth.storage import get_session_storage  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from testcontainers.core.docker_client import DockerClient  # noqa: E402

# mypy: disable-error-code="import-untyped"
from testcontainers.postgres import PostgresContainer  # noqa: E402

from src.infrastructure.auth.setup import auth  # noqa: E402
from src.infrastructure.config.settings import get_settings  # noqa: E402
from src.infrastructure.database import session as database_session  # noqa: E402
from src.infrastructure.database.session import Base, async_session  # noqa: E402
from src.interfaces.main import app  # noqa: E402
from src.modules.role.service import seed_default_roles  # noqa: E402

TEST_DATABASE_URL = get_settings().DATABASE_URL

backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))


def is_docker_running() -> bool:
    try:
        DockerClient()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def pg_container():
    if not is_docker_running():
        pytest.skip("Docker is required, but not running")

    with PostgresContainer() as pg:
        yield pg


@pytest_asyncio.fixture(scope="function")
async def test_db_url(pg_container):
    host = pg_container.get_container_host_ip()
    port_to_expose = 5432
    if hasattr(pg_container, "port_to_expose"):
        port_to_expose = pg_container.port_to_expose
    port = pg_container.get_exposed_port(port_to_expose)

    db = "test"
    user = "test"
    password = "test"
    if hasattr(pg_container, "POSTGRES_USER"):
        user = pg_container.POSTGRES_USER
    if hasattr(pg_container, "POSTGRES_PASSWORD"):
        password = pg_container.POSTGRES_PASSWORD
    if hasattr(pg_container, "POSTGRES_DB"):
        db = pg_container.POSTGRES_DB

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@pytest_asyncio.fixture(scope="function")
async def test_db_engine(test_db_url):
    engine = create_async_engine(test_db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_db_engine):
    test_session = sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with test_session() as session:  # type: ignore
        yield session


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db):
    yield test_db


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    app.dependency_overrides = {}

    async def override_get_db():
        yield test_db

    app.dependency_overrides[async_session] = override_get_db

    os.environ["POSTGRES_SERVER"] = "localhost"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides = {}


@pytest_asyncio.fixture(scope="function")
async def fresh_db(test_db):
    yield test_db


@pytest_asyncio.fixture(scope="function")
async def seeded_db(test_db):
    await seed_default_roles(test_db)
    yield test_db


@pytest.fixture
def startup_against_test_db(monkeypatch, test_db_engine):
    monkeypatch.setattr(
        database_session, "local_session", sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    )


@pytest.fixture(autouse=True)
def isolated_login_limiter(monkeypatch: pytest.MonkeyPatch):
    # Every test client shares one IP and the limiter lives in process memory, so a lockout
    # left behind would throttle the other auth tests in this worker.
    monkeypatch.setattr(auth.runtime.lockout, "backend", MemoryRateLimiterBackend())


@pytest.fixture(autouse=True)
def isolated_session_store(monkeypatch: pytest.MonkeyPatch):
    # Each test's database restarts user ids at 1, so sessions left in the shared in-memory store
    # would belong to the next test's users and skew counts such as Log out everywhere.
    manager = auth.sessions
    monkeypatch.setattr(manager, "storage", get_session_storage(prefix=manager.storage.prefix))
    if manager.csrf_storage is not None:
        monkeypatch.setattr(manager, "csrf_storage", get_session_storage(prefix=manager.csrf_storage.prefix))
