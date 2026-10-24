"""Database connections: async SQLAlchemy engine for Postgres, motor client for MongoDB."""

from collections.abc import AsyncIterator
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one session per request."""
    async with get_sessionmaker()() as session:
        yield session


@lru_cache
def get_mongo_client() -> AsyncIOMotorClient:
    settings = get_settings()
    timeout_ms = int(settings.db_check_timeout_seconds * 1000)
    return AsyncIOMotorClient(
        settings.mongo_url, serverSelectionTimeoutMS=timeout_ms, tz_aware=True
    )


def get_mongo_db() -> AsyncIOMotorDatabase:
    return get_mongo_client()[get_settings().mongo_db_name]


async def close_connections() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    if get_mongo_client.cache_info().currsize:
        get_mongo_client().close()
