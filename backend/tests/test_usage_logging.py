"""Pricing table and the usage-logging provider wrappers (no databases needed)."""

from pathlib import Path

import pytest

from app.llm.base import ChatMessage, LLMError, LLMResponse, ToolCall
from app.llm.embeddings import FakeEmbeddingProvider
from app.llm.fake_provider import FakeProvider
from app.llm.pricing import ModelPrice, PricingTable, get_pricing
from app.llm.usage import (
    InMemoryUsageLogger,
    LLMCallRecord,
    LoggedEmbeddingProvider,
    LoggedProvider,
    MongoUsageLogger,
)

PRICING = PricingTable(
    {
        "gpt-4o": ModelPrice(2.5, 10.0),
        "gpt-4o-mini": ModelPrice(0.15, 0.6),
        "scripted": ModelPrice(1.0, 2.0),
        "fake-hashed-bow": ModelPrice(0.02, 0.0),
    }
)
USER = [ChatMessage(role="user", content="hello")]


def _response(**overrides: object) -> LLMResponse:
    base = {
        "text": "Hi [1]",
        "input_tokens": 1000,
        "output_tokens": 500,
        "latency_ms": 42.0,
        "model": "scripted",
        "provider": "fake",
    }
    return LLMResponse(**{**base, **overrides})  # type: ignore[arg-type]


def _logged(
    provider: FakeProvider, sink: InMemoryUsageLogger, feature: str = "chat"
) -> LoggedProvider:
    return LoggedProvider(
        provider,
        feature=feature,
        usage_logger=sink,
        pricing=PRICING,
        prompt_version="rag-v1",  # type: ignore[arg-type]
    )


# --- pricing ------------------------------------------------------------------------------


def test_cost_uses_exact_then_longest_prefix_match() -> None:
    assert PRICING.estimate("gpt-4o", 1_000_000, 1_000_000).usd == 12.5
    # "gpt-4o-mini-2024-07-18" must match gpt-4o-mini, not the shorter gpt-4o
    assert PRICING.estimate("gpt-4o-mini-2024-07-18", 1_000_000, 0).usd == 0.15
    assert PRICING.estimate("models/gpt-4o", 0, 100_000).usd == 1.0


def test_unknown_model_is_flagged_not_guessed() -> None:
    estimate = PRICING.estimate("mystery-model-9", 5000, 5000)
    assert (estimate.usd, estimate.known) == (0.0, False)


def test_pricing_table_loads_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "pricing.yaml"
    path.write_text("models:\n  m1: { input: 3, output: 6 }\n  embed: { input: 0.5 }\n")

    table = PricingTable.from_yaml(path)

    assert table.estimate("m1", 2_000_000, 1_000_000).usd == 12.0
    assert table.estimate("embed", 1_000_000, 0).usd == 0.5


def test_shipped_pricing_file_covers_the_default_models() -> None:
    table = get_pricing()
    for model in ["gpt-5.4-mini", "claude-haiku-5-5", "gemini-2.5-flash", "text-embedding-3-small"]:
        assert table.price_for(model) is not None, model


# --- LoggedProvider -----------------------------------------------------------------------


async def test_successful_chat_is_logged_with_tokens_cost_and_prompt_version() -> None:
    sink = InMemoryUsageLogger()
    provider = _logged(FakeProvider(script=[_response()]), sink)

    response = await provider.chat(USER)

    assert response.text == "Hi [1]"
    [record] = sink.records
    assert (record.feature, record.provider, record.model) == ("chat", "fake", "scripted")
    assert (record.input_tokens, record.output_tokens, record.latency_ms) == (1000, 500, 42.0)
    assert record.estimated_cost_usd == pytest.approx(0.002)  # 1000*1 + 500*2 per million
    assert record.success and record.cost_known and record.prompt_version == "rag-v1"


async def test_failed_call_is_logged_and_the_error_still_raised() -> None:
    sink = InMemoryUsageLogger()
    provider = _logged(FakeProvider(script=[]), sink, feature="review")

    with pytest.raises(LLMError, match="script exhausted"):
        await provider.chat_with_tools(USER, tools=[])

    [record] = sink.records
    assert record.feature == "review"
    assert not record.success
    assert record.error == "LLMError: FakeProvider script exhausted"
    assert record.input_tokens == 0 and record.estimated_cost_usd == 0


async def test_tool_calls_pass_through_unchanged() -> None:
    sink = InMemoryUsageLogger()
    call = ToolCall(id="c1", name="search_policies", arguments={"query": "kyc"})
    provider = _logged(FakeProvider(script=[_response(tool_calls=[call])]), sink, "review")

    response = await provider.chat_with_tools(USER, tools=[])

    assert response.tool_calls == [call]
    assert sink.records[0].feature == "review"


async def test_stream_is_logged_once_after_completion_with_usage() -> None:
    sink = InMemoryUsageLogger()
    provider = _logged(FakeProvider(), sink)

    stream = provider.stream_chat(USER)
    first = await anext(stream)
    assert sink.records == [], "nothing is logged until the stream finishes"
    rest = [delta async for delta in stream]

    assert first + "".join(rest) == stream.response.text  # type: ignore[union-attr]
    [record] = sink.records
    assert record.success and record.output_tokens == len(stream.response.text.split())  # type: ignore[union-attr]
    assert stream.response.input_tokens == record.input_tokens  # type: ignore[union-attr]


async def test_embedding_calls_are_logged_with_token_counts() -> None:
    sink = InMemoryUsageLogger()
    embedder = LoggedEmbeddingProvider(
        FakeEmbeddingProvider(dim=8), usage_logger=sink, pricing=PRICING
    )

    vectors = await embedder.embed(["proof of address", "record retention policy"])

    assert len(vectors) == 2 and len(vectors[0]) == 8
    [record] = sink.records
    assert (record.feature, record.provider, record.model) == (
        "embedding",
        "fake",
        "fake-hashed-bow",
    )
    assert record.input_tokens == 6 and record.output_tokens == 0


async def test_mongo_logger_never_raises_when_storage_fails() -> None:
    class BrokenCollection:
        async def insert_one(self, _doc: object) -> None:
            raise ConnectionError("mongo is down")

    logger = MongoUsageLogger({"llm_calls": BrokenCollection()})  # type: ignore[arg-type]

    await logger.log(LLMCallRecord(feature="chat", provider="fake", model="m"))  # no exception
