from typing import Literal

from pydantic import BaseModel

ComponentState = Literal["ok", "error"]


class ComponentStatus(BaseModel):
    status: ComponentState
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: ComponentStatus
    mongo: ComponentStatus
