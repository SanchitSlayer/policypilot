"""Aggregate llm_calls for the Admin dashboard in a single MongoDB round trip."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.schemas.usage import DailyUsage, UsageBreakdown, UsageStats, UsageSummary


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db["llm_calls"].create_indexes(
        [
            IndexModel([("timestamp", DESCENDING)]),
            IndexModel([("provider", ASCENDING), ("timestamp", DESCENDING)]),
            IndexModel([("feature", ASCENDING), ("timestamp", DESCENDING)]),
        ]
    )
    await db["conversations"].create_indexes(
        [
            IndexModel([("conversation_id", ASCENDING)], unique=True),
            IndexModel([("updated_at", DESCENDING)]),
        ]
    )


# Accumulators shared by every grouping. $percentile needs MongoDB 7.0+.
_STATS = {
    "requests": {"$sum": 1},
    "errors": {"$sum": {"$cond": ["$success", 0, 1]}},
    "input_tokens": {"$sum": "$input_tokens"},
    "output_tokens": {"$sum": "$output_tokens"},
    "cost_usd": {"$sum": "$estimated_cost_usd"},
    "unpriced_requests": {"$sum": {"$cond": ["$cost_known", 0, 1]}},
    "avg_latency_ms": {"$avg": "$latency_ms"},
    "latency": {"$percentile": {"input": "$latency_ms", "p": [0.5, 0.95], "method": "approximate"}},
}


def _stats(doc: dict[str, Any]) -> dict[str, Any]:
    requests = doc.get("requests", 0)
    latency = doc.get("latency") or [None, None]
    rounded = lambda v: round(v, 1) if v is not None else None  # noqa: E731
    return {
        "requests": requests,
        "errors": doc.get("errors", 0),
        "error_rate": round(doc.get("errors", 0) / requests, 4) if requests else 0.0,
        "input_tokens": doc.get("input_tokens", 0),
        "output_tokens": doc.get("output_tokens", 0),
        "total_tokens": doc.get("input_tokens", 0) + doc.get("output_tokens", 0),
        "cost_usd": round(doc.get("cost_usd", 0.0), 6),
        "unpriced_requests": doc.get("unpriced_requests", 0),
        "avg_latency_ms": rounded(doc.get("avg_latency_ms")),
        "p50_latency_ms": rounded(latency[0]),
        "p95_latency_ms": rounded(latency[1]),
    }


def _day_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


async def usage_summary(db: AsyncIOMotorDatabase, start: date, end: date) -> UsageSummary:
    """Usage between `start` and `end` inclusive (UTC days)."""
    since = datetime.combine(start, time.min, tzinfo=UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    day = {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "UTC"}}

    pipeline = [
        {"$match": {"timestamp": {"$gte": since, "$lt": until}}},
        {
            "$facet": {
                "totals": [{"$group": {"_id": None, **_STATS}}],
                "by_provider": [
                    {"$group": {"_id": "$provider", **_STATS}},
                    {"$sort": {"requests": -1, "_id": 1}},
                ],
                "by_feature": [
                    {"$group": {"_id": "$feature", **_STATS}},
                    {"$sort": {"requests": -1, "_id": 1}},
                ],
                "daily": [
                    {
                        "$group": {
                            "_id": {"day": day, "provider": "$provider"},
                            "requests": {"$sum": 1},
                            "errors": {"$sum": {"$cond": ["$success", 0, 1]}},
                            "cost_usd": {"$sum": "$estimated_cost_usd"},
                            "tokens": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}},
                        }
                    }
                ],
            }
        },
    ]
    [result] = await db["llm_calls"].aggregate(pipeline).to_list(length=1)

    days: dict[str, dict[str, Any]] = {
        d.isoformat(): {"requests": 0, "errors": 0, "cost_usd": 0.0, "tokens": 0, "by_provider": {}}
        for d in _day_range(start, end)
    }
    for row in result["daily"]:
        bucket = days.get(row["_id"]["day"])
        if bucket is None:
            continue
        bucket["requests"] += row["requests"]
        bucket["errors"] += row["errors"]
        bucket["cost_usd"] += row["cost_usd"]
        bucket["tokens"] += row["tokens"]
        bucket["by_provider"][row["_id"]["provider"]] = row["requests"]

    totals = result["totals"][0] if result["totals"] else {}
    return UsageSummary(
        start=start,
        end=end,
        totals=UsageStats(**_stats(totals)),
        by_provider=[UsageBreakdown(key=r["_id"], **_stats(r)) for r in result["by_provider"]],
        by_feature=[UsageBreakdown(key=r["_id"], **_stats(r)) for r in result["by_feature"]],
        daily=[
            DailyUsage(
                date=date.fromisoformat(d),
                requests=b["requests"],
                errors=b["errors"],
                cost_usd=round(b["cost_usd"], 6),
                total_tokens=b["tokens"],
                by_provider=b["by_provider"],
            )
            for d, b in days.items()
        ],
    )
