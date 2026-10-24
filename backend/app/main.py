import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, chat, conversations, documents, health, review
from app.core.config import get_settings
from app.core.db import close_connections, get_mongo_db
from app.core.logging import configure_logging
from app.services.usage_stats import ensure_indexes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        await ensure_indexes(get_mongo_db())
    except Exception:  # the API still serves documents and chat; /health reports Mongo
        logger.warning("Could not create MongoDB indexes", exc_info=True)
    yield
    await close_connections()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(review.router)
    app.include_router(conversations.router)
    app.include_router(admin.router)
    return app


app = create_app()
