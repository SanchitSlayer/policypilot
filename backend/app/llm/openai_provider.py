import json
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

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


def to_openai_messages(messages: list[ChatMessage], system: str | None) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for message in messages:
        if message.role == "tool":
            converted.append(
                {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
            )
        elif message.role == "assistant" and message.tool_calls:
            converted.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        else:
            converted.append({"role": message.role, "content": message.content})
    return converted


def parse_arguments(raw: str | None) -> dict[str, Any]:
    """Tool arguments arrive as a JSON string; invalid JSON is passed on for the agent to
    reject, rather than crashing the provider."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"__invalid_json__": raw}
    return parsed if isinstance(parsed, dict) else {"__invalid_json__": raw}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, max_tokens: int, timeout: float) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self._max_tokens = max_tokens

    def _common(self, temperature: float | None) -> dict[str, Any]:
        params: dict[str, Any] = {"model": self.model, "max_completion_tokens": self._max_tokens}
        if temperature is not None:
            params["temperature"] = temperature
        return params

    def stream_chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatStream:
        async def chunks() -> AsyncIterator[str | LLMResponse]:
            try:
                stream = await self._client.chat.completions.create(
                    messages=to_openai_messages(messages, system),  # type: ignore[arg-type]
                    stream=True,
                    stream_options={"include_usage": True},
                    **self._common(temperature),
                )
                async for event in stream:
                    if event.choices and event.choices[0].delta.content:
                        yield event.choices[0].delta.content
                    if event.usage:
                        yield LLMResponse(
                            text="",
                            input_tokens=event.usage.prompt_tokens,
                            output_tokens=event.usage.completion_tokens,
                            model=event.model or self.model,
                            provider=self.name,
                        )
            except Exception as exc:
                raise LLMError(f"OpenAI streaming request failed: {exc}") from exc

        return ChatStream(self.name, self.model, chunks())

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return await self._complete(messages, system, temperature, tools=None)

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system: str | None = None,
    ) -> LLMResponse:
        return await self._complete(messages, system, None, tools=tools)

    async def _complete(
        self,
        messages: list[ChatMessage],
        system: str | None,
        temperature: float | None,
        tools: list[ToolSpec] | None,
    ) -> LLMResponse:
        params = self._common(temperature)
        if tools:
            params["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        started = time.perf_counter()
        try:
            completion = await self._client.chat.completions.create(
                messages=to_openai_messages(messages, system),  # type: ignore[arg-type]
                **params,
            )
        except Exception as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        choice = completion.choices[0]
        tool_calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=parse_arguments(call.function.arguments),
            )
            for call in (choice.message.tool_calls or [])
            if call.type == "function"
        ]
        usage = completion.usage
        return LLMResponse(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=elapsed_ms(started),
            model=completion.model,
            provider=self.name,
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason,
        )
