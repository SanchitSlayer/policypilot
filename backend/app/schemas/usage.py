from datetime import date

from pydantic import BaseModel


class UsageStats(BaseModel):
    requests: int = 0
    errors: int = 0
    error_rate: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_requests: int = 0  # calls to models missing from config/pricing.yaml
    avg_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None


class UsageBreakdown(UsageStats):
    key: str  # provider or feature name


class DailyUsage(BaseModel):
    date: date
    requests: int
    errors: int
    cost_usd: float
    total_tokens: int
    by_provider: dict[str, int]  # requests per provider that day


class UsageSummary(BaseModel):
    start: date
    end: date
    totals: UsageStats
    by_provider: list[UsageBreakdown]
    by_feature: list[UsageBreakdown]
    daily: list[DailyUsage]
