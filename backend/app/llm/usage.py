"""Usage logging for every LLM and embedding call, in one place.

Wrap a provider with `LoggedProvider` (or an embedder with `LoggedEmbeddingProvider`) and each
call writes one record (tokens, latency, estimated cost, success/error) to the usage logger.
Logging never breaks a request: storage failures are reported to the app log and dropped.
"""

import logging
import time
from collections.abc import AsyncIterator, Awaitable
from datetime import UTC, datetime
from typing import Literal, Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.llm.base import ChatMessage, ChatStream, LLMProvider, LLMResponse, ToolSpec
from app.llm.embeddings import EmbeddingProvider
from app.llm.pricing import PricingTable
from app.services.chunking import get_encoding

logger = logging.getLogger(__name__)

Feature = Literal["chat", "review", "embedding"]
MAX_ERROR_CHARS = 500


class LLMCallRecord(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    feature: Feature
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0
    cost_known: bool = True
    success: bool = True
    error: str | None = None  # exception type and message only; prompts are never logged
    prompt_version: str | None = None


class UsageLogger(Protocol):
    async def log(self, record: LLMCallRecord) -> None: ...


class MongoUsageLogger:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db["llm_calls"]

    async def log(self, record: LLMCallRecord) -> None:
        try:
            await self._collection.insert_one(record.model_dump())
        except Exception:  # never fail the user's request because logging failed
            logger.warning("Could not store LLM usage record", exc_info=True)


class InMemoryUsageLogger:
    """For tests and scripts that should not touch MongoDB."""

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    async def log(self, record: LLMCallRecord) -> None:
        self.records.append(record)


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


class _Recorder:
    def __init__(
        self,
        usage_logger: UsageLogger,
        pricing: PricingTable,
        feature: Feature,
        provider: str,
        prompt_version: str | None,
    ) -> None:
        self._logger = usage_logger
        self._pricing = pricing
        self._feature: Feature = feature
        self._provider = provider
        self._prompt_version = prompt_version

    async def success(
        self, model: str, input_tokens: int, output_tokens: int, latency_ms: float
    ) -> None:
        cost = self._pricing.estimate(model, input_tokens, output_tokens)
        await self._logger.log(
            LLMCallRecord(
                feature=self._feature,
                provider=self._provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated_cost_usd=cost.usd,
                cost_known=cost.known,
                prompt_version=self._prompt_version,
            )
        )

    async def failure(self, model: str, exc: BaseException, started: float) -> None:
        await self._logger.log(
            LLMCallRecord(
                feature=self._feature,
                provider=self._provider,
                model=model,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                success=False,
                error=_error_text(exc),
                prompt_version=self._prompt_version,
            )
        )


class LoggedProvider(LLMProvider):
    """Decorator that logs every call of the wrapped provider."""

    def __init__(
        self,
        inner: LLMProvider,
        *,
        feature: Feature,
        usage_logger: UsageLogger,
        pricing: PricingTable,
        prompt_version: str | None = None,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = inner.model
        self._record = _Recorder(usage_logger, pricing, feature, inner.name, prompt_version)

    async def _logged(self, call: Awaitable[LLMResponse]) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = await call
        except Exception as exc:
            await self._record.failure(self.model, exc, started)
            raise
        await self._record.success(
            response.model, response.input_tokens, response.output_tokens, response.latency_ms
        )
        return response

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return await self._logged(self.inner.chat(messages, system, temperature))

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system: str | None = None,
    ) -> LLMResponse:
        return await self._logged(self.inner.chat_with_tools(messages, tools, system))

    def stream_chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatStream:
        inner_stream = self.inner.stream_chat(messages, system, temperature)

        async def chunks() -> AsyncIterator[str | LLMResponse]:
            started = time.perf_counter()
            try:
                async for delta in inner_stream:
                    yield delta
            except Exception as exc:
                await self._record.failure(self.model, exc, started)
                raise
            final = inner_stream.response
            if final is not None:
                await self._record.success(
                    final.model, final.input_tokens, final.output_tokens, final.latency_ms
                )
                yield final  # hand the usage on to the outer ChatStream

        return ChatStream(self.name, self.model, chunks())


class LoggedEmbeddingProvider:
    """Logs embedding calls. Token counts are estimated with the tokenizer (cl100k), which
    matches OpenAI's embedding models."""

    def __init__(
        self,
        inner: EmbeddingProvider,
        *,
        usage_logger: UsageLogger,
        pricing: PricingTable,
        encoding_name: str = "cl100k_base",
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = inner.model
        self.dim = inner.dim
        self._encoding_name = encoding_name
        self._record = _Recorder(usage_logger, pricing, "embedding", inner.name, None)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        try:
            vectors = await self.inner.embed(texts)
        except Exception as exc:
            await self._record.failure(self.model, exc, started)
            raise
        encoding = get_encoding(self._encoding_name)
        tokens = sum(len(encoding.encode(text)) for text in texts)
        latency = round((time.perf_counter() - started) * 1000, 1)
        await self._record.success(self.model, tokens, 0, latency)
        return vectors


def with_usage_logging(
    provider: LLMProvider,
    feature: Feature,
    usage_logger: UsageLogger,
    prompt_version: str | None = None,
) -> LLMProvider:
    from app.llm.pricing import get_pricing

    return LoggedProvider(
        provider,
        feature=feature,
        usage_logger=usage_logger,
        pricing=get_pricing(),
        prompt_version=prompt_version,
    )
