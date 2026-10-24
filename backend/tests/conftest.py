import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.api.documents import get_embedder, get_session_factory
from app.core.config import get_settings
from app.core.db import get_db_session
from app.llm.embeddings import FakeEmbeddingProvider
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://policypilot:policypilot@localhost:5432/policypilot_test",
)


@pytest.fixture
def fake_embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=get_settings().embedding_dim)


@pytest.fixture
async def client(fake_embedder: FakeEmbeddingProvider) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
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
