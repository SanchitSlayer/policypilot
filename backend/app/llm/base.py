"""Provider-neutral types and the LLMProvider interface every provider implements."""

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    # Opaque provider data that must be echoed back on the next turn
    # (e.g. Gemini's thought_signature). Never shown to users.
    metadata: dict[str, Any] = Field(default_factory=dict, repr=False)


class ChatMessage(BaseModel):
    """One turn in a conversation, normalised across providers.

    - user / assistant: plain text in `content`
    - assistant may also carry `tool_calls` it made
    - tool: the result of one tool call (`tool_call_id`, `name`, `content`)
    """

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments object


class LLMResponse(BaseModel):
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    model: str
    provider: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str | None = None


class LLMError(RuntimeError):
    """A provider call failed (network, auth, quota, malformed response)."""


class ProviderNotConfiguredError(LLMError):
    """The requested provider is missing its API key or model name."""


class ChatStream:
    """Async iterator of text deltas. After iteration finishes, `.response` holds the
    full text and token usage, so callers (and the usage logger) get both."""

    def __init__(self, provider: str, model: str, chunks: AsyncIterator[str | LLMResponse]):
        self.provider = provider
        self.model = model
        self._chunks = chunks
        self._started = time.perf_counter()
        self._parts: list[str] = []
        self.response: LLMResponse | None = None

    def __aiter__(self) -> "ChatStream":
        return self

    async def __anext__(self) -> str:
        while True:
            try:
                item = await anext(self._chunks)
            except StopAsyncIteration:
                if self.response is None:
                    self.response = self._build_response(None)
                raise
            if isinstance(item, LLMResponse):  # final usage record from the provider
                self.response = self._build_response(item)
                continue
            if item:
                self._parts.append(item)
                return item

    def _build_response(self, final: LLMResponse | None) -> LLMResponse:
        return LLMResponse(
            text="".join(self._parts),
            input_tokens=final.input_tokens if final else 0,
            output_tokens=final.output_tokens if final else 0,
            latency_ms=round((time.perf_counter() - self._started) * 1000, 1),
            model=final.model if final else self.model,
            provider=self.provider,
            stop_reason=final.stop_reason if final else None,
        )


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def stream_chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatStream:
        """Stream the assistant reply as text deltas."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Return the full assistant reply."""

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system: str | None = None,
    ) -> LLMResponse:
        """One model step with tools available. Tool calls come back normalised in
        `LLMResponse.tool_calls`; the caller runs them and sends `tool` messages back."""


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
