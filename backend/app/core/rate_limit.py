"""Per-client rate limits for the expensive endpoints (LLM calls and uploads).

Limits come from settings ("20/minute" syntax). Storage defaults to in-process memory, which
is per instance; set RATE_LIMIT_STORAGE_URI to a Redis URL to share counts across instances.
Behind Cloud Run, uvicorn's --proxy-headers makes request.client the real client IP.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.rate_limit_storage_uri,
    enabled=_settings.rate_limit_enabled,
)


def chat_limit() -> str:
    return get_settings().rate_limit_chat


def review_limit() -> str:
    return get_settings().rate_limit_review


def upload_limit() -> str:
    return get_settings().rate_limit_upload


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceeded)
    return JSONResponse(
        {"detail": f"Too many requests ({exc.detail}). Please wait and try again."},
        status_code=429,
        headers={"Retry-After": "60"},
    )
