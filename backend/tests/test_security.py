"""Request size limits, security headers, CORS, rate limits and log redaction."""

import logging
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_provider_factory
from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.core.logging import RedactingFilter, redact
from app.core.rate_limit import limiter
from app.llm.fake_provider import FakeProvider
from app.main import app


async def test_oversized_json_body_is_rejected_before_the_handler(client: AsyncClient) -> None:
    response = await client.post(
        "/chat",
        content=b'{"question": "' + b"x" * 70_000 + b'"}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


async def test_oversized_chunked_body_is_rejected(client: AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"question": "'
        for _ in range(10):
            yield b"x" * 10_000
        yield b'"}'

    response = await client.post(
        "/chat", content=chunks(), headers={"content-type": "application/json"}
    )

    assert response.status_code in (400, 413)  # FastAPI wraps body read errors as 400


async def test_uploads_get_the_larger_upload_limit(client: AsyncClient) -> None:
    response = await client.post(
        "/documents", files={"file": ("notes.txt", b"x" * 200_000, "text/plain")}
    )

    assert response.status_code == 415, "reached the handler: not cut off by the 64 KB JSON limit"


async def test_security_headers_are_set(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


async def test_cors_allows_only_configured_origins(client: AsyncClient) -> None:
    preflight = {
        "access-control-request-method": "POST",
        "access-control-request-headers": "content-type",
    }
    allowed = await client.options(
        "/chat", headers={"origin": "http://localhost:3000", **preflight}
    )
    blocked = await client.options("/chat", headers={"origin": "https://evil.example", **preflight})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked.headers


async def test_chat_is_rate_limited_per_client(
    db_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rate_limit, "get_settings", lambda: Settings(_env_file=None, rate_limit_chat="2/minute")
    )
    app.dependency_overrides[get_provider_factory] = lambda: lambda _name: FakeProvider()
    app.dependency_overrides[get_settings] = lambda: get_settings()
    limiter.reset()
    limiter.enabled = True

    statuses = [
        (await db_client.post("/chat", json={"question": "anything"})).status_code for _ in range(3)
    ]
    blocked = await db_client.post("/chat/stream", json={"question": "anything"})

    assert statuses == [200, 200, 429]
    assert blocked.status_code == 429, "the limit is shared by /chat and /chat/stream per client"
    assert "Too many requests" in blocked.json()["detail"]
    assert blocked.headers["retry-after"] == "60"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("contact priya.sharma@example.com now", "contact [email] now"),
        ("PAN ABCDE1234F on file", "PAN [pan] on file"),
        ("aadhaar 1234 5678 9012 seen", "aadhaar [aadhaar] seen"),
        ("call +91 9876543210 today", "call [phone] today"),
        ("document 3f2c retained for 5 years", "document 3f2c retained for 5 years"),
    ],
)
def test_redact_masks_personal_data(raw: str, expected: str) -> None:
    assert redact(raw) == expected


def test_redacting_filter_rewrites_formatted_log_records() -> None:
    record = logging.LogRecord(
        "app", logging.ERROR, __file__, 1, "Upload failed for %s", ("a.b@example.com",), None
    )

    RedactingFilter().filter(record)

    assert record.getMessage() == "Upload failed for [email]"
