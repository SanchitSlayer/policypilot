"""FastAPI dependencies shared across routers (overridden in tests)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import get_db_session, get_mongo_db, get_sessionmaker
from app.llm.base import LLMProvider
from app.llm.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider
from app.llm.pricing import get_pricing
from app.llm.registry import get_provider
from app.llm.usage import LoggedEmbeddingProvider, MongoUsageLogger, UsageLogger

ProviderFactory = Callable[[str], LLMProvider]


def get_mongo_database() -> AsyncIOMotorDatabase:
    return get_mongo_db()


MongoDep = Annotated[AsyncIOMotorDatabase, Depends(get_mongo_database)]


def get_usage_logger(db: MongoDep) -> UsageLogger:
    return MongoUsageLogger(db)


UsageLoggerDep = Annotated[UsageLogger, Depends(get_usage_logger)]


def get_embedder(usage_logger: UsageLoggerDep) -> EmbeddingProvider:
    try:
        embedder = get_embedding_provider()
    except EmbeddingError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return LoggedEmbeddingProvider(embedder, usage_logger=usage_logger, pricing=get_pricing())


def get_provider_factory() -> ProviderFactory:
    """Returns raw providers by name; callers wrap them with usage logging."""
    return get_provider


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory for background work that outlives the request session."""
    return get_sessionmaker()


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EmbedderDep = Annotated[EmbeddingProvider, Depends(get_embedder)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
ProviderFactoryDep = Annotated[ProviderFactory, Depends(get_provider_factory)]
