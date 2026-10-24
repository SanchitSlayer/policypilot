"""Deterministic, offline provider for tests and local development without API keys."""

import re
from collections.abc import AsyncIterator, Iterable

from app.llm.base import ChatMessage, ChatStream, LLMError, LLMProvider, LLMResponse, ToolSpec
from app.llm.prompts import NO_ANSWER_TEXT

_SOURCE_RE = re.compile(
    r"^\[(\d+)\] (.+?), p\.(\d+):\n(.+?)(?=\n\n\[\d+\] |\n\nQuestion: |\Z)", re.M | re.S
)


def _count_tokens(text: str) -> int:
    return len(text.split())


def fake_rag_answer(user_message: str) -> str:
    """Quote the first sentence of up to two sources and cite them, or say no answer."""
    sources = _SOURCE_RE.findall(user_message)
    if not sources:
        return NO_ANSWER_TEXT
    lines = ["According to the uploaded documents:"]
    for number, _title, _page, text in sources[:2]:
        first_sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
        lines.append(f"- {first_sentence} [{number}]")
    return "\n".join(lines)


class FakeProvider(LLMProvider):
    """With no script, answers RAG prompts deterministically from the sources it was given.
    With a `script`, returns the scripted responses in order (used to test the agent loop)."""

    name = "fake"

    def __init__(self, script: Iterable[LLMResponse] | None = None, model: str = "fake-model"):
        self.model = model
        self._script = list(script) if script is not None else None
        self.calls: list[list[ChatMessage]] = []

    def _next(self, messages: list[ChatMessage], system: str | None) -> LLMResponse:
        self.calls.append(list(messages))
        if self._script is not None:
            if not self._script:
                raise LLMError("FakeProvider script exhausted")
            return self._script.pop(0)
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        text = fake_rag_answer(last_user)
        prompt_tokens = _count_tokens(system or "") + sum(
            _count_tokens(m.content) for m in messages
        )
        return LLMResponse(
            text=text,
            input_tokens=prompt_tokens,
            output_tokens=_count_tokens(text),
            latency_ms=1.0,
            model=self.model,
            provider=self.name,
            stop_reason="end_turn",
        )

    def stream_chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatStream:
        async def chunks() -> AsyncIterator[str | LLMResponse]:
            response = self._next(messages, system)
            for word in re.findall(r"\S+\s*", response.text):
                yield word
            yield response

        return ChatStream(self.name, self.model, chunks())

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return self._next(messages, system)

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system: str | None = None,
    ) -> LLMResponse:
        return self._next(messages, system)
