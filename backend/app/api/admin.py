from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import MongoDep
from app.schemas.usage import UsageSummary
from app.services.usage_stats import usage_summary

router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_DAYS = 30
MAX_DAYS = 366


@router.get("/usage", response_model=UsageSummary)
async def get_usage(
    db: MongoDep,
    start: Annotated[
        date | None, Query(alias="from", description="First day (UTC), YYYY-MM-DD")
    ] = None,
    end: Annotated[date | None, Query(alias="to", description="Last day (UTC), inclusive")] = None,
) -> UsageSummary:
    """Requests, tokens, estimated cost, latency percentiles and error rate, by provider,
    feature and day. Defaults to the last 30 days."""
    end = end or datetime.now(UTC).date()
    start = start or end - timedelta(days=DEFAULT_DAYS - 1)
    if start > end:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="'from' must not be after 'to'."
        )
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"The date range can be at most {MAX_DAYS} days.",
        )
    return await usage_summary(db, start, end)
