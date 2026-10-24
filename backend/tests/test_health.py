from httpx import AsyncClient

from app.api.health import get_mongo_check, get_postgres_check
from app.main import app
from app.schemas.health import ComponentStatus
from app.services.health import HealthCheck


def _check(result: ComponentStatus) -> HealthCheck:
    async def run() -> ComponentStatus:
        return result

    return run


OK = ComponentStatus(status="ok", latency_ms=1.0)
DOWN = ComponentStatus(status="error", error="connection refused")


def _override(postgres: ComponentStatus, mongo: ComponentStatus) -> None:
    app.dependency_overrides[get_postgres_check] = lambda: _check(postgres)
    app.dependency_overrides[get_mongo_check] = lambda: _check(mongo)


async def test_health_ok_when_both_databases_respond(client: AsyncClient) -> None:
    _override(OK, OK)

    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"]["status"] == "ok"
    assert body["mongo"]["status"] == "ok"


async def test_health_degraded_when_a_database_is_down(client: AsyncClient) -> None:
    _override(OK, DOWN)

    response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["mongo"] == {"status": "error", "latency_ms": None, "error": "connection refused"}
