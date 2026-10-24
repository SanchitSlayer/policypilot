"""Offline tests for the provider layer: message conversion, streaming wrapper, registry."""

import pytest

from app.core.config import Settings
from app.llm.anthropic_provider import to_anthropic_messages
from app.llm.base import ChatMessage, ChatStream, LLMResponse, ProviderNotConfiguredError, ToolCall
from app.llm.fake_provider import FakeProvider, fake_rag_answer
from app.llm.gemini_provider import to_gemini_contents
from app.llm.openai_provider import parse_arguments, to_openai_messages
from app.llm.prompts import NO_ANSWER_TEXT, build_rag_user_message
from app.llm.registry import build_provider

CALL_A = ToolCall(id="call_a", name="search_policies", arguments={"query": "retention"})
CALL_B = ToolCall(
    id="call_b",
    name="record_finding",
    arguments={"clause_id": "c1"},
    metadata={"thought_signature": b"sig"},
)
TOOL_TURN = [
    ChatMessage(role="user", content="Review the contract."),
    ChatMessage(role="assistant", content="Checking.", tool_calls=[CALL_A, CALL_B]),
    ChatMessage(role="tool", tool_call_id="call_a", name="search_policies", content="[]"),
    ChatMessage(role="tool", tool_call_id="call_b", name="record_finding", content="ok"),
]


def test_openai_conversion_keeps_system_tool_calls_and_results() -> None:
    converted = to_openai_messages(TOOL_TURN, system="Be precise.")

    assert converted[0] == {"role": "system", "content": "Be precise."}
    assert converted[2]["tool_calls"][0]["function"] == {
        "name": "search_policies",
        "arguments": '{"query": "retention"}',
    }
    assert [m["role"] for m in converted] == ["system", "user", "assistant", "tool", "tool"]
    assert converted[3] == {"role": "tool", "tool_call_id": "call_a", "content": "[]"}


def test_anthropic_conversion_merges_consecutive_tool_results() -> None:
    converted = to_anthropic_messages(TOOL_TURN)

    assert [m["role"] for m in converted] == ["user", "assistant", "user"]
    assert [b["type"] for b in converted[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in converted[2]["content"]] == ["call_a", "call_b"]


def test_gemini_conversion_echoes_thought_signature_and_groups_results() -> None:
    contents = to_gemini_contents(TOOL_TURN)

    assert [c.role for c in contents] == ["user", "model", "user"]
    model_parts = contents[1].parts or []
    assert model_parts[2].function_call is not None
    assert model_parts[2].thought_signature == b"sig"
    results = contents[2].parts or []
    assert [p.function_response.name for p in results if p.function_response] == [
        "search_policies",
        "record_finding",
    ]


def test_invalid_tool_argument_json_is_preserved_for_the_agent_to_reject() -> None:
    assert parse_arguments('{"query": "kyc"}') == {"query": "kyc"}
    assert parse_arguments("{not json") == {"__invalid_json__": "{not json"}
    assert parse_arguments(None) == {}


async def test_chat_stream_collects_text_and_final_usage() -> None:
    stream = FakeProvider().stream_chat(
        [ChatMessage(role="user", content="Question with no sources")]
    )

    deltas = [delta async for delta in stream]

    assert "".join(deltas) == NO_ANSWER_TEXT
    assert stream.response is not None
    assert stream.response.text == NO_ANSWER_TEXT
    assert stream.response.output_tokens == len(NO_ANSWER_TEXT.split())


async def test_chat_stream_without_usage_record_still_builds_response() -> None:
    async def chunks():  # type: ignore[no-untyped-def]
        yield "Hello "
        yield "world"

    stream = ChatStream("test", "m", chunks())
    assert [d async for d in stream] == ["Hello ", "world"]
    assert stream.response == LLMResponse(
        text="Hello world",
        model="m",
        provider="test",
        latency_ms=stream.response.latency_ms if stream.response else 0,
    )


def test_fake_rag_answer_cites_the_sources_it_was_given() -> None:
    class Source:
        def __init__(self, title: str, page: int, content: str) -> None:
            self.document_title, self.page_number, self.content = title, page, content

    message = build_rag_user_message(
        "What is valid ID?",
        [Source("KYC", 3, "Passport is valid. More text."), Source("KYC", 4, "Aadhaar too.")],
    )

    assert fake_rag_answer(message) == (
        "According to the uploaded documents:\n- Passport is valid. [1]\n- Aadhaar too. [2]"
    )


@pytest.mark.parametrize(
    ("name", "missing"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
    ],
)
def test_registry_reports_missing_api_key(name: str, missing: str) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key=None,
    )
    with pytest.raises(ProviderNotConfiguredError, match=missing):
        build_provider(name, settings)


def test_registry_reports_missing_model_and_unknown_provider() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="sk-test", anthropic_chat_model="")  # type: ignore[call-arg]
    with pytest.raises(ProviderNotConfiguredError, match="ANTHROPIC_CHAT_MODEL"):
        build_provider("anthropic", settings)
    with pytest.raises(ProviderNotConfiguredError, match="Unknown provider"):
        build_provider("mistral", settings)
