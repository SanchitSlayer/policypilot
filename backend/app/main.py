import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api import admin, chat, conversations, documents, health, review
from app.core.config import get_settings
from app.core.db import close_connections, get_mongo_db
from app.core.logging import configure_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
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
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Added innermost first: CORS stays outermost so even 413/429 errors are readable by the UI.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=settings.max_json_body_kb * 1024,
        upload_limit=settings.max_upload_bytes + 1024 * 1024,  # multipart overhead
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # no cookies or auth headers are used
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        max_age=600,
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(review.router)
    app.include_router(conversations.router)
    app.include_router(admin.router)
    return app


app = create_app()
