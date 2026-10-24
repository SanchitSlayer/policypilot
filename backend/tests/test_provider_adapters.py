"""Provider adapters against stub SDK clients: request shape and response normalisation.

No network: each provider's `_client` is replaced with a stub that records the request and
returns objects shaped like the real SDK responses.
"""

from collections.abc import AsyncIterator
from types import SimpleNamespace as NS
from typing import Any

import pytest

from app.core.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ChatMessage, LLMError, ToolSpec
from app.llm.embeddings import (
    EmbeddingError,
    FakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
    build_embedding_provider,
)
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAIProvider

USER = [ChatMessage(role="user", content="What is the retention period?")]
TOOL = ToolSpec(
    name="search_policies",
    description="Search",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}},
)


class Recorder:
    """Callable stub: records kwargs, returns (or raises) a preset result."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result, self.error, self.calls = result, error, []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


# --- OpenAI -------------------------------------------------------------------------------


def _openai(create: Recorder) -> OpenAIProvider:
    provider = OpenAIProvider(api_key="sk-test", model="gpt-test", max_tokens=256, timeout=5)
    provider._client = NS(chat=NS(completions=NS(create=create)))  # type: ignore[assignment]
    return provider


async def test_openai_chat_with_tools_normalises_tool_calls_and_usage() -> None:
    completion = NS(
        model="gpt-test-2026",
        usage=NS(prompt_tokens=120, completion_tokens=30),
        choices=[
            NS(
                finish_reason="tool_calls",
                message=NS(
                    content=None,
                    tool_calls=[
                        NS(
                            id="call_1",
                            type="function",
                            function=NS(name="search_policies", arguments='{"query": "retention"}'),
                        ),
                        NS(
                            id="call_2",
                            type="function",
                            function=NS(name="search_policies", arguments="{broken"),
                        ),
                    ],
                ),
            )
        ],
    )
    create = Recorder(completion)

    response = await _openai(create).chat_with_tools(USER, [TOOL], system="Be precise.")

    assert (response.text, response.input_tokens, response.output_tokens) == ("", 120, 30)
    assert (response.model, response.provider, response.stop_reason) == (
        "gpt-test-2026",
        "openai",
        "tool_calls",
    )
    assert response.tool_calls[0].arguments == {"query": "retention"}
    assert response.tool_calls[1].arguments == {"__invalid_json__": "{broken"}
    request = create.calls[0]
    assert request["model"] == "gpt-test" and request["max_completion_tokens"] == 256
    assert "temperature" not in request, "temperature is only sent when configured"
    assert request["messages"][0] == {"role": "system", "content": "Be precise."}
    assert request["tools"][0]["function"]["name"] == "search_policies"


async def test_openai_stream_yields_deltas_and_final_usage() -> None:
    events = [
        NS(choices=[NS(delta=NS(content="Five "))], usage=None, model="gpt-test"),
        NS(choices=[NS(delta=NS(content="years [1]"))], usage=None, model="gpt-test"),
        NS(choices=[], usage=NS(prompt_tokens=50, completion_tokens=4), model="gpt-test"),
    ]
    create = Recorder(_aiter(events))

    stream = _openai(create).stream_chat(USER, temperature=0.2)
    text = "".join([delta async for delta in stream])

    assert text == "Five years [1]"
    assert stream.response is not None
    assert (stream.response.input_tokens, stream.response.output_tokens) == (50, 4)
    assert create.calls[0]["stream_options"] == {"include_usage": True}
    assert create.calls[0]["temperature"] == 0.2


async def test_openai_errors_are_wrapped() -> None:
    provider = _openai(Recorder(error=RuntimeError("401 invalid api key")))
    with pytest.raises(LLMError, match="OpenAI request failed: 401 invalid api key"):
        await provider.chat(USER)


# --- Anthropic ----------------------------------------------------------------------------


class _AnthropicStream:
    def __init__(self, texts: list[str], final: Any) -> None:
        self.text_stream = _aiter(texts)
        self._final = final

    async def __aenter__(self) -> "_AnthropicStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get_final_message(self) -> Any:
        return self._final


def _anthropic(create: Recorder | None = None, stream: Any = None) -> AnthropicProvider:
    provider = AnthropicProvider(
        api_key="sk-ant-test", model="claude-test", max_tokens=512, timeout=5
    )
    provider._client = NS(messages=NS(create=create, stream=stream))  # type: ignore[assignment]
    return provider


async def test_anthropic_chat_with_tools_reads_text_and_tool_use_blocks() -> None:
    message = NS(
        model="claude-test",
        stop_reason="tool_use",
        usage=NS(input_tokens=300, output_tokens=40),
        content=[
            NS(type="text", text="Let me search."),
            NS(type="tool_use", id="toolu_1", name="search_policies", input={"query": "consent"}),
        ],
    )
    create = Recorder(message)

    response = await _anthropic(create).chat_with_tools(USER, [TOOL], system="Review it.")

    assert response.text == "Let me search."
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("toolu_1", "search_policies", {"query": "consent"})
    ]
    assert (response.input_tokens, response.output_tokens, response.stop_reason) == (
        300,
        40,
        "tool_use",
    )
    request = create.calls[0]
    assert request["system"] == "Review it." and request["max_tokens"] == 512
    assert request["tools"][0]["input_schema"] == TOOL.parameters
    assert "temperature" not in request


async def test_anthropic_stream_uses_final_message_usage() -> None:
    final = NS(
        model="claude-test", stop_reason="end_turn", usage=NS(input_tokens=80, output_tokens=6)
    )
    calls: list[dict[str, Any]] = []

    def stream(**kwargs: Any) -> _AnthropicStream:
        calls.append(kwargs)
        return _AnthropicStream(["Records are kept ", "five years [1]."], final)

    chat_stream = _anthropic(stream=stream).stream_chat(USER, system="sys")
    text = "".join([d async for d in chat_stream])

    assert text == "Records are kept five years [1]."
    assert chat_stream.response is not None
    assert (chat_stream.response.input_tokens, chat_stream.response.output_tokens) == (80, 6)
    assert calls[0]["system"] == "sys"


async def test_anthropic_errors_are_wrapped() -> None:
    with pytest.raises(LLMError, match="Anthropic request failed: overloaded"):
        await _anthropic(Recorder(error=RuntimeError("overloaded"))).chat(USER)


# --- Gemini -------------------------------------------------------------------------------


def _gemini(
    generate: Recorder | None = None, generate_stream: Recorder | None = None
) -> GeminiProvider:
    provider = GeminiProvider(api_key="gm-test", model="gemini-test", max_tokens=128, timeout=5)
    provider._client = NS(  # type: ignore[assignment]
        aio=NS(models=NS(generate_content=generate, generate_content_stream=generate_stream))
    )
    return provider


async def test_gemini_chat_with_tools_keeps_thought_signatures_and_skips_thoughts() -> None:
    response = NS(
        model_version="gemini-test-001",
        usage_metadata=NS(prompt_token_count=200, candidates_token_count=25),
        candidates=[
            NS(
                finish_reason="STOP",
                content=NS(
                    parts=[
                        NS(
                            text="internal reasoning",
                            thought=True,
                            function_call=None,
                            thought_signature=None,
                        ),
                        NS(
                            text="Searching.",
                            thought=False,
                            function_call=None,
                            thought_signature=None,
                        ),
                        NS(
                            text=None,
                            thought=False,
                            function_call=NS(
                                id=None, name="search_policies", args={"query": "breach"}
                            ),
                            thought_signature=b"sig-1",
                        ),
                    ]
                ),
            )
        ],
    )
    generate = Recorder(response)

    result = await _gemini(generate).chat_with_tools(USER, [TOOL], system="sys")

    assert result.text == "Searching.", "thought parts are not part of the answer"
    [call] = result.tool_calls
    assert call.name == "search_policies" and call.arguments == {"query": "breach"}
    assert call.id.startswith("call_"), "missing ids are generated"
    assert call.metadata == {"thought_signature": b"sig-1"}
    assert (result.input_tokens, result.output_tokens, result.model) == (200, 25, "gemini-test-001")
    config = generate.calls[0]["config"]
    assert config.system_instruction == "sys" and config.max_output_tokens == 128
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].parameters_json_schema == TOOL.parameters


async def test_gemini_stream_reads_usage_from_last_chunk() -> None:
    chunks = [
        NS(text="Report within ", usage_metadata=None, model_version="gemini-test"),
        NS(
            text="six hours [1].",
            usage_metadata=NS(prompt_token_count=90, candidates_token_count=7),
            model_version="gemini-test",
        ),
    ]
    stream = _gemini(generate_stream=Recorder(_aiter(chunks))).stream_chat(USER)

    text = "".join([d async for d in stream])

    assert text == "Report within six hours [1]."
    assert stream.response is not None
    assert (stream.response.input_tokens, stream.response.output_tokens) == (90, 7)


async def test_gemini_errors_are_wrapped() -> None:
    with pytest.raises(LLMError, match="Gemini request failed: 429"):
        await _gemini(Recorder(error=RuntimeError("429 RESOURCE_EXHAUSTED"))).chat(USER)


# --- Embeddings ---------------------------------------------------------------------------


def _openai_embedder(create: Recorder, dim: int = 3) -> OpenAIEmbeddingProvider:
    embedder = OpenAIEmbeddingProvider(api_key="sk-test", model="embed-test", dim=dim)
    embedder._client = NS(embeddings=NS(create=create))  # type: ignore[assignment]
    return embedder


async def test_openai_embeddings_are_returned_in_input_order() -> None:
    data = [NS(index=1, embedding=[0.0, 1.0, 0.0]), NS(index=0, embedding=[1.0, 0.0, 0.0])]
    create = Recorder(NS(data=data))

    vectors = await _openai_embedder(create).embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert create.calls[0] == {"model": "embed-test", "input": ["first", "second"], "dimensions": 3}
    assert await _openai_embedder(create).embed([]) == []


async def test_openai_embeddings_reject_wrong_dimension_and_wrap_errors() -> None:
    wrong = Recorder(NS(data=[NS(index=0, embedding=[1.0, 0.0])]))
    with pytest.raises(EmbeddingError, match="not 3-dimensional"):
        await _openai_embedder(wrong).embed(["x"])
    with pytest.raises(EmbeddingError, match="request failed: timeout"):
        await _openai_embedder(Recorder(error=TimeoutError("timeout"))).embed(["x"])


def test_embedding_provider_factory_explains_misconfiguration() -> None:
    base = {"_env_file": None, "embedding_dim": 8}
    assert isinstance(
        build_embedding_provider(Settings(**base, embedding_provider="fake")), FakeEmbeddingProvider
    )  # type: ignore[arg-type]
    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY is not set"):
        build_embedding_provider(Settings(**base, embedding_provider="openai", openai_api_key=None))  # type: ignore[arg-type]
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL must be set"):
        build_embedding_provider(
            Settings(**base, embedding_provider="openai", openai_api_key="k", embedding_model="")
        )  # type: ignore[arg-type]
    with pytest.raises(EmbeddingError, match="Unknown EMBEDDING_PROVIDER"):
        build_embedding_provider(Settings(**base, embedding_provider="cohere"))  # type: ignore[arg-type]
