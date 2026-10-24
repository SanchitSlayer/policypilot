import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

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


def to_gemini_contents(messages: list[ChatMessage]) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in messages:
        if message.role == "tool":
            part = types.Part(
                function_response=types.FunctionResponse(
                    id=message.tool_call_id,
                    name=message.name,
                    response={"result": message.content},
                )
            )
            previous = contents[-1] if contents else None
            if (
                previous
                and previous.role == "user"
                and previous.parts
                and previous.parts[0].function_response
            ):
                previous.parts.append(part)  # all results of one model turn go together
            else:
                contents.append(types.Content(role="user", parts=[part]))
        elif message.role == "assistant":
            parts: list[types.Part] = []
            if message.content:
                parts.append(types.Part(text=message.content))
            parts.extend(
                types.Part(
                    function_call=types.FunctionCall(id=c.id, name=c.name, args=c.arguments),
                    thought_signature=c.metadata.get("thought_signature"),
                )
                for c in message.tool_calls
            )
            contents.append(types.Content(role="model", parts=parts))
        else:
            contents.append(types.Content(role="user", parts=[types.Part(text=message.content)]))
    return contents


def _usage(response: types.GenerateContentResponse) -> tuple[int, int]:
    usage = response.usage_metadata
    if usage is None:
        return 0, 0
    return usage.prompt_token_count or 0, usage.candidates_token_count or 0


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, max_tokens: int, timeout: float) -> None:
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout * 1000))
        )
        self.model = model
        self._max_tokens = max_tokens

    def _config(
        self,
        system: str | None,
        temperature: float | None,
        tools: list[ToolSpec] | None = None,
    ) -> types.GenerateContentConfig:
        config: dict[str, Any] = {"max_output_tokens": self._max_tokens}
        if system:
            config["system_instruction"] = system
        if temperature is not None:
            config["temperature"] = temperature
        if tools:
            config["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ]
            # We run the agent loop ourselves; the SDK must not call Python functions.
            config["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
                disable=True
            )
        return types.GenerateContentConfig(**config)

    def stream_chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> ChatStream:
        async def chunks() -> AsyncIterator[str | LLMResponse]:
            last: types.GenerateContentResponse | None = None
            try:
                stream = await self._client.aio.models.generate_content_stream(
                    model=self.model,
                    contents=to_gemini_contents(messages),
                    config=self._config(system, temperature),
                )
                async for chunk in stream:
                    last = chunk
                    if chunk.text:
                        yield chunk.text
            except Exception as exc:
                raise LLMError(f"Gemini streaming request failed: {exc}") from exc
            if last is not None:
                input_tokens, output_tokens = _usage(last)
                yield LLMResponse(
                    text="",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=last.model_version or self.model,
                    provider=self.name,
                )

        return ChatStream(self.name, self.model, chunks())

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        return await self._complete(messages, self._config(system, temperature))

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        system: str | None = None,
    ) -> LLMResponse:
        return await self._complete(messages, self._config(system, None, tools))

    async def _complete(
        self, messages: list[ChatMessage], config: types.GenerateContentConfig
    ) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=to_gemini_contents(messages), config=config
            )
        except Exception as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        candidate = response.candidates[0] if response.candidates else None
        parts = (candidate.content.parts if candidate and candidate.content else None) or []
        text = "".join(part.text for part in parts if part.text and not part.thought)
        tool_calls = [
            ToolCall(
                id=part.function_call.id or f"call_{uuid.uuid4().hex[:12]}",
                name=part.function_call.name or "",
                arguments=dict(part.function_call.args or {}),
                metadata=(
                    {"thought_signature": part.thought_signature} if part.thought_signature else {}
                ),
            )
            for part in parts
            if part.function_call
        ]
        input_tokens, output_tokens = _usage(response)
        finish = candidate.finish_reason if candidate else None
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms(started),
            model=response.model_version or self.model,
            provider=self.name,
            tool_calls=tool_calls,
            stop_reason=str(finish) if finish else None,
        )
