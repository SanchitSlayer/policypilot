"""Connectivity checks for the backing databases."""

import asyncio
import time
from collections.abc import Awaitable, Callable

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine, get_mongo_client
from app.schemas.health import ComponentStatus

HealthCheck = Callable[[], Awaitable[ComponentStatus]]


async def _timed(probe: Callable[[], Awaitable[object]]) -> ComponentStatus:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(probe(), timeout=get_settings().db_check_timeout_seconds)
    except Exception as exc:  # any failure means the dependency is unhealthy
        message = str(exc) or type(exc).__name__
        return ComponentStatus(status="error", error=message)
    latency = round((time.perf_counter() - started) * 1000, 2)
    return ComponentStatus(status="ok", latency_ms=latency)


async def check_postgres() -> ComponentStatus:
    async def probe() -> None:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    return await _timed(probe)


async def check_mongo() -> ComponentStatus:
    return await _timed(lambda: get_mongo_client().admin.command("ping"))
