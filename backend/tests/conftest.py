import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.api.chat import get_conversation_store
from app.api.deps import get_embedder, get_mongo_database, get_session_factory, get_usage_logger
from app.core.config import get_settings
from app.core.db import get_db_session
from app.llm.embeddings import FakeEmbeddingProvider
from app.llm.usage import InMemoryUsageLogger
from app.main import app
from app.services.conversations import InMemoryConversationStore
from app.services.usage_stats import ensure_indexes

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_MONGO_URL = os.getenv("TEST_MONGO_URL", "mongodb://localhost:27017")
TEST_MONGO_DB = "policypilot_test"
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://policypilot:policypilot@localhost:5432/policypilot_test",
)


@pytest.fixture
def fake_embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=get_settings().embedding_dim)


@pytest.fixture
def usage_logger() -> InMemoryUsageLogger:
    return InMemoryUsageLogger()


@pytest.fixture
async def client(
    fake_embedder: FakeEmbeddingProvider, usage_logger: InMemoryUsageLogger
) -> AsyncIterator[AsyncClient]:
    """API client that never touches the developer's real databases unless a test opts in."""
    store = InMemoryConversationStore()
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_usage_logger] = lambda: usage_logger
    app.dependency_overrides[get_conversation_store] = lambda: store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


# --- Postgres-backed tests --------------------------------------------------------------


async def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    conn = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port or 5432,
        database="postgres",
        timeout=3,
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", parsed.database
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    """Create the test database (if needed) and migrate it to head, once per session."""
    try:
        asyncio.run(_ensure_database(TEST_DATABASE_URL))
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        pytest.skip(
            f"Postgres not reachable for DB tests ({exc}); run `docker compose up postgres`"
        )

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield TEST_DATABASE_URL


@pytest.fixture
async def session_factory(
    migrated_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db_client(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncClient:
    """API client whose request sessions and background ingestion use the test database."""

    async def test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = test_session
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    return client


# --- MongoDB-backed tests ---------------------------------------------------------------


@pytest.fixture
async def mongo_db() -> AsyncIterator[AsyncIOMotorDatabase]:
    """A clean `policypilot_test` database with indexes, also used by the API under test."""
    mongo = AsyncIOMotorClient(TEST_MONGO_URL, serverSelectionTimeoutMS=2000, tz_aware=True)
    try:
        await mongo.admin.command("ping")
    except Exception as exc:
        mongo.close()
        pytest.skip(f"MongoDB not reachable ({exc}); run `docker compose up mongo`")
    await mongo.drop_database(TEST_MONGO_DB)
    db = mongo[TEST_MONGO_DB]
    await ensure_indexes(db)
    app.dependency_overrides[get_mongo_database] = lambda: db
    yield db
    mongo.close()
