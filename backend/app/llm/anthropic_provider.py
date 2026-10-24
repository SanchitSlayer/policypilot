import time
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from app.llm.base import (
    ChatMessage,
    ChatStream,
    LLMError,
    LLMProvider,
    LLMResponse,
    ToolCall,
    ToolSpec,
    elapsed_ms,
)


def to_anthropic_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Convert to Anthropic format. Consecutive tool results are merged into one user turn,
    because Anthropic expects all results for an assistant turn in a single message."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            previous = converted[-1] if converted else None
            if (
                previous
                and previous["role"] == "user"
                and isinstance(previous["content"], list)
                and previous["content"]
                and previous["content"][0].get("type") == "tool_result"
            ):
                previous["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
        elif message.role == "assistant" and message.tool_calls:
            blocks: list[dict[str, Any]] = []
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            blocks.extend(
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                for c in message.tool_calls
            )
            converted.append({"role": "assistant", "content": blocks})
        else:
            converted.append({"role": message.role, "content": message.content})
    return converted


class AnthropicProvider(LLMProvider):
    """Claude via the Messages API.

    `temperature` is accepted for interface compatibility but not sent: current Claude
    models and SDK versions no longer take sampling parameters.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int, timeout: float) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout)
        self.model = model
        self._max_tokens = max_tokens

    def _params(self, messages: list[ChatMessage], system: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": to_anthropic_messages(messages),
        }
        if system:
            params["system"] = system
        return params

    def stream_chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatStream:
        async def chunks() -> AsyncIterator[str | LLMResponse]:
            try:
                async with self._client.messages.stream(**self._params(messages, system)) as s:
                    async for text in s.text_stream:
                        yield text
                    final = await s.get_final_message()
            except Exception as exc:
                raise LLMError(f"Anthropic streaming request failed: {exc}") from exc
            yield LLMResponse(
                text="",
                input_tokens=final.usage.input_tokens,
                output_tokens=final.usage.output_tokens,
                model=final.model,
                provider=self.name,
                stop_reason=final.stop_reason,
            )

        return ChatStream(self.name, self.model, chunks())

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return await self._complete(self._params(messages, system))

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system: str | None = None,
    ) -> LLMResponse:
        params = self._params(messages, system)
        params["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        return await self._complete(params)

    async def _complete(self, params: dict[str, Any]) -> LLMResponse:
        started = time.perf_counter()
        try:
            message = await self._client.messages.create(**params)
        except Exception as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc

        text = "".join(block.text for block in message.content if block.type == "text")
        tool_calls = [
            ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
            for block in message.content
            if block.type == "tool_use"
        ]
        return LLMResponse(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=elapsed_ms(started),
            model=message.model,
            provider=self.name,
            tool_calls=tool_calls,
            stop_reason=message.stop_reason,
        )
