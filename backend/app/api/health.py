import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.schemas.health import HealthResponse
from app.services.health import HealthCheck, check_mongo, check_postgres

router = APIRouter(tags=["health"])


def get_postgres_check() -> HealthCheck:
    return check_postgres


def get_mongo_check() -> HealthCheck:
    return check_mongo


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response,
    postgres_check: Annotated[HealthCheck, Depends(get_postgres_check)],
    mongo_check: Annotated[HealthCheck, Depends(get_mongo_check)],
) -> HealthResponse:
    """Report connectivity to Postgres and MongoDB. Returns 503 if either is down."""
    postgres, mongo = await asyncio.gather(postgres_check(), mongo_check())
    healthy = postgres.status == "ok" and mongo.status == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", postgres=postgres, mongo=mongo)
