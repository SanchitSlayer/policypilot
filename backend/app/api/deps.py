"""FastAPI dependencies shared across routers (overridden in tests)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import get_db_session, get_sessionmaker
from app.llm.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider


def get_embedder() -> EmbeddingProvider:
    try:
        return get_embedding_provider()
    except EmbeddingError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory for background work that outlives the request session."""
    return get_sessionmaker()


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EmbedderDep = Annotated[EmbeddingProvider, Depends(get_embedder)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
