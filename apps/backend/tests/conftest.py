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

# Disable the testcontainers Ryuk reaper. Under `pytest -n auto`, each xdist worker
# is a separate process that spins up its own Ryuk container, and Docker Desktop
# chokes mapping all their ports at once ("Port mapping ... port 8080 is not
# available"). Testcontainers' own `with` blocks still clean up on normal exit.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from crudauth import get_password_hash  # noqa: E402
from faker import Faker  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from testcontainers.core.docker_client import DockerClient  # noqa: E402

# mypy: disable-error-code="import-untyped"
from testcontainers.postgres import PostgresContainer  # noqa: E402

from src.infrastructure.auth.dependencies import get_current_superuser, get_current_user  # noqa: E402
from src.infrastructure.config.settings import get_settings  # noqa: E402
from src.infrastructure.database.session import Base, async_session  # noqa: E402
from src.interfaces.main import app  # noqa: E402
from src.modules.role.models import Role  # noqa: E402
from src.modules.user.models import User  # noqa: E402

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


@pytest_asyncio.fixture
async def test_role(db_session: AsyncSession):
    role = Role(name="user", description="Default user role")
    db_session.add(role)
    await db_session.commit()
    return {"id": role.id, "name": role.name}


@pytest_asyncio.fixture
async def second_test_role(db_session: AsyncSession):
    role = Role(name="moderator", description="Moderator role")
    db_session.add(role)
    await db_session.commit()
    return {"id": role.id, "name": role.name}


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_role: dict):
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"u{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        role_id=test_role["id"],
        profile_image_url="https://example.com/test.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "role_id": user.role_id,
        "role_name": test_role["name"],
        "password": "Password123!",
        "profile_image_url": user.profile_image_url,
    }


@pytest_asyncio.fixture
async def test_user_2(db_session: AsyncSession, test_role: dict):
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"u{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("Password123!"),
        is_superuser=False,
        role_id=test_role["id"],
        profile_image_url="https://example.com/test2.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "role_id": user.role_id,
        "role_name": test_role["name"],
        "password": "Password123!",
        "profile_image_url": user.profile_image_url,
    }


@pytest_asyncio.fixture
async def test_superuser(db_session: AsyncSession, test_role: dict):
    fake = Faker()
    user = User(
        name=fake.name(),
        username=f"su{fake.random_int(10000, 99999)}",
        email=fake.email(),
        hashed_password=get_password_hash("SuperuserPass123!"),
        is_superuser=True,
        role_id=test_role["id"],
        profile_image_url="https://example.com/superuser.jpg",
    )
    db_session.add(user)
    await db_session.commit()
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "role_id": user.role_id,
        "role_name": test_role["name"],
        "password": "SuperuserPass123!",
        "profile_image_url": user.profile_image_url,
    }


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, test_user: dict):

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return client


@pytest_asyncio.fixture
async def auth_client_2(client: AsyncClient, test_user_2: dict):

    async def override_get_current_user():
        return test_user_2

    app.dependency_overrides[get_current_user] = override_get_current_user
    return client


@pytest_asyncio.fixture
async def superuser_auth_client(client: AsyncClient, test_superuser: dict):

    async def override_get_current_user():
        return test_superuser

    async def override_get_current_superuser():
        return test_superuser

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_superuser] = override_get_current_superuser
    return client


@pytest.fixture(autouse=True)
def mock_oauth_settings(monkeypatch):
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8000")
