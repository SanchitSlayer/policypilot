"""MongoDB-backed: chat history, usage records written by real requests, admin aggregation."""

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.chat import get_conversation_store
from app.api.deps import get_provider_factory, get_usage_logger
from app.core.config import get_settings
from app.llm.embeddings import FakeEmbeddingProvider
from app.llm.fake_provider import FakeProvider
from app.llm.usage import LLMCallRecord, MongoUsageLogger
from app.main import app
from app.models import Document, DocumentStatus
from app.services.conversations import MongoConversationStore
from app.services.ingestion import ingest_document
from app.utils.simple_pdf import make_pdf

ADDRESS_PAGE = (
    "Proof of address. Officially valid documents for proof of address are the passport, "
    "driving licence, voter identity card and Aadhaar number."
)


@pytest.fixture
async def mongo_client(
    db_client: AsyncClient,
    mongo_db: AsyncIOMotorDatabase,
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> AsyncClient:
    """API client using Mongo-backed history and usage logging, fake LLM and one document."""
    app.dependency_overrides[get_conversation_store] = lambda: MongoConversationStore(mongo_db)
    app.dependency_overrides[get_usage_logger] = lambda: MongoUsageLogger(mongo_db)
    app.dependency_overrides[get_provider_factory] = lambda: lambda _name: FakeProvider()
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"retrieval_min_score": 0.05}
    )
    async with session_factory() as session:
        doc = Document(filename="kyc.pdf", title="KYC Direction", status=DocumentStatus.PROCESSING)
        session.add(doc)
        await session.commit()
        doc_id = doc.id
    await ingest_document(
        doc_id,
        make_pdf([ADDRESS_PAGE]),
        session_factory=session_factory,
        embedder=fake_embedder,
        settings=get_settings(),
    )
    return db_client


# --- conversations ------------------------------------------------------------------------


async def test_conversations_are_stored_with_citations_and_can_be_reloaded(
    mongo_client: AsyncClient,
) -> None:
    first = (
        await mongo_client.post(
            "/chat",
            json={"question": "Which documents are valid proof of address?", "provider": "fake"},
        )
    ).json()
    cid = first["conversation_id"]
    await mongo_client.post(
        "/chat", json={"question": "and for companies?", "conversation_id": cid, "provider": "fake"}
    )

    listing = (await mongo_client.get("/conversations")).json()
    detail = (await mongo_client.get(f"/conversations/{cid}")).json()

    assert [(c["conversation_id"], c["title"], c["message_count"]) for c in listing] == [
        (cid, "Which documents are valid proof of address?", 4)
    ]
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    answer = detail["messages"][1]
    assert answer["content"] == first["answer"]
    assert answer["provider"] == "fake"
    assert answer["citations"][0]["document_title"] == "KYC Direction"
    assert answer["citations"][0]["page_number"] == 1


async def test_follow_up_prompt_includes_history_from_mongo(
    mongo_client: AsyncClient, mongo_db: AsyncIOMotorDatabase
) -> None:
    provider = FakeProvider()
    app.dependency_overrides[get_provider_factory] = lambda: lambda _name: provider
    first = (await mongo_client.post("/chat", json={"question": "proof of address"})).json()

    await mongo_client.post(
        "/chat", json={"question": "anything else?", "conversation_id": first["conversation_id"]}
    )

    assert [m.role for m in provider.calls[1]] == ["user", "assistant", "user"]
    assert provider.calls[1][0].content == "proof of address"


async def test_delete_conversation(mongo_client: AsyncClient) -> None:
    cid = (await mongo_client.post("/chat", json={"question": "proof of address"})).json()[
        "conversation_id"
    ]

    assert (await mongo_client.delete(f"/conversations/{cid}")).status_code == 204
    assert (await mongo_client.get(f"/conversations/{cid}")).status_code == 404
    assert (await mongo_client.delete(f"/conversations/{cid}")).status_code == 404
    assert (await mongo_client.get("/conversations")).json() == []


# --- usage records from real requests ----------------------------------------------------


async def test_chat_request_writes_usage_records(
    mongo_client: AsyncClient, mongo_db: AsyncIOMotorDatabase
) -> None:
    await mongo_client.post("/chat", json={"question": "valid proof of address documents"})

    records = await mongo_db["llm_calls"].find({}, {"_id": 0}).to_list(length=10)

    assert [r["feature"] for r in records] == ["chat"]  # embeddings are faked in tests
    record = records[0]
    assert record["provider"] == "fake" and record["model"] == "fake-model"
    assert record["success"] is True and record["prompt_version"] == "rag-v1"
    assert record["input_tokens"] > 0 and record["output_tokens"] > 0
    assert record["timestamp"].tzinfo is not None


# --- admin aggregation -------------------------------------------------------------------


def _record(day: date, provider: str, latency: float, **kw: object) -> LLMCallRecord:
    base = {
        "timestamp": datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
        "feature": "chat",
        "provider": provider,
        "model": f"{provider}-model",
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_ms": latency,
        "estimated_cost_usd": 0.01,
    }
    return LLMCallRecord(**{**base, **kw})  # type: ignore[arg-type]


async def test_admin_usage_aggregates_by_provider_feature_and_day(
    client: AsyncClient, mongo_db: AsyncIOMotorDatabase
) -> None:
    d1, d2 = date(2026, 10, 1), date(2026, 10, 3)
    logger = MongoUsageLogger(mongo_db)
    for record in [
        _record(d1, "openai", 100),
        _record(d1, "openai", 200),
        _record(
            d2,
            "openai",
            300,
            success=False,
            error="LLMError: 429",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
        ),
        _record(d2, "anthropic", 1000, feature="review", estimated_cost_usd=0.05),
        _record(d2, "gemini", 400, cost_known=False, estimated_cost_usd=0),
        _record(date(2026, 9, 30), "openai", 50),  # outside the range
    ]:
        await logger.log(record)

    body = (
        await client.get("/admin/usage", params={"from": "2026-10-01", "to": "2026-10-03"})
    ).json()

    totals = body["totals"]
    assert totals["requests"] == 5
    assert totals["errors"] == 1 and totals["error_rate"] == 0.2
    assert totals["total_tokens"] == 4 * 150
    assert totals["cost_usd"] == pytest.approx(0.07)
    assert totals["unpriced_requests"] == 1
    assert totals["avg_latency_ms"] == 400.0
    assert 200 <= totals["p50_latency_ms"] <= 400
    assert totals["p95_latency_ms"] >= 400

    by_provider = {b["key"]: b for b in body["by_provider"]}
    # most requests first; ties by name, so the order is stable
    assert list(by_provider) == ["openai", "anthropic", "gemini"]
    assert by_provider["openai"]["requests"] == 3 and by_provider["openai"][
        "error_rate"
    ] == pytest.approx(1 / 3, abs=1e-4)
    assert by_provider["anthropic"]["cost_usd"] == pytest.approx(0.05)
    assert {b["key"]: b["requests"] for b in body["by_feature"]} == {"chat": 4, "review": 1}

    assert [d["date"] for d in body["daily"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert [d["requests"] for d in body["daily"]] == [2, 0, 3]  # empty day filled with zeros
    assert body["daily"][2]["by_provider"] == {"openai": 1, "anthropic": 1, "gemini": 1}


async def test_admin_usage_defaults_to_last_30_days_and_handles_no_data(
    client: AsyncClient, mongo_db: AsyncIOMotorDatabase
) -> None:
    body = (await client.get("/admin/usage")).json()

    today = datetime.now(UTC).date()
    assert body["end"] == today.isoformat()
    assert body["start"] == (today - timedelta(days=29)).isoformat()
    assert len(body["daily"]) == 30
    assert body["totals"]["requests"] == 0 and body["totals"]["p95_latency_ms"] is None
    assert body["by_provider"] == []


@pytest.mark.parametrize(
    "params",
    [{"from": "2026-10-05", "to": "2026-10-01"}, {"from": "2024-01-01", "to": "2026-01-01"}],
)
async def test_admin_usage_rejects_bad_ranges(
    client: AsyncClient, mongo_db: AsyncIOMotorDatabase, params: dict[str, str]
) -> None:
    assert (await client.get("/admin/usage", params=params)).status_code == 422


async def test_unique_conversation_index_exists(mongo_db: AsyncIOMotorDatabase) -> None:
    indexes = await mongo_db["conversations"].index_information()
    assert any(spec.get("unique") for spec in indexes.values())


async def test_chat_with_persist_false_is_not_saved_to_history(
    mongo_client: AsyncClient, mongo_db: AsyncIOMotorDatabase
) -> None:
    response = await mongo_client.post(
        "/chat", json={"question": "proof of address documents", "persist": False}
    )

    assert response.status_code == 200 and response.json()["citations"]
    assert (await mongo_client.get("/conversations")).json() == []
    assert await mongo_db["llm_calls"].count_documents({"feature": "chat"}) == 1, "still logged"
