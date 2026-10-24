"""Retrieval and chat endpoints against real pgvector, with fake embeddings and a fake LLM."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.chat import get_provider_factory
from app.core.config import Settings, get_settings
from app.llm.base import ProviderNotConfiguredError
from app.llm.embeddings import FakeEmbeddingProvider
from app.llm.fake_provider import FakeProvider
from app.llm.prompts import NO_ANSWER_TEXT
from app.main import app
from app.models import Document, DocumentStatus
from app.services.conversations import InMemoryConversationStore, get_conversation_store
from app.services.ingestion import ingest_document
from app.services.retrieval import retrieve
from app.utils.simple_pdf import make_pdf

ADDRESS_PAGE = (
    "Proof of address. Officially valid documents for proof of address are the passport, "
    "driving licence, voter identity card and Aadhaar number."
)
RETENTION_PAGE = (
    "Record retention. Regulated entities shall preserve records of transactions with "
    "customers for at least five years after the business relationship ends."
)
LENDING_PAGE = (
    "Digital lending. Loan disbursals shall be made directly into the bank account of the "
    "borrower without any pass-through account of a lending service provider."
)


def _settings(**overrides: object) -> Settings:
    base = {"retrieval_min_score": 0.05, "retrieval_top_k": 3, "default_llm_provider": "fake"}
    return get_settings().model_copy(update={**base, **overrides})


async def _ingest(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: FakeEmbeddingProvider,
    title: str,
    pages: list[str],
    status: DocumentStatus | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        document = Document(filename=f"{title}.pdf", title=title, status=DocumentStatus.PROCESSING)
        session.add(document)
        await session.commit()
        document_id = document.id
    await ingest_document(
        document_id,
        make_pdf(pages),
        session_factory=session_factory,
        embedder=embedder,
        settings=get_settings(),
    )
    if status is not None:
        async with session_factory() as session:
            doc = await session.get(Document, document_id)
            assert doc is not None
            doc.status = status
            await session.commit()
    return document_id


@pytest.fixture
async def corpus(
    session_factory: async_sessionmaker[AsyncSession], fake_embedder: FakeEmbeddingProvider
) -> dict[str, uuid.UUID]:
    return {
        "kyc": await _ingest(
            session_factory, fake_embedder, "KYC Direction", [ADDRESS_PAGE, RETENTION_PAGE]
        ),
        "lending": await _ingest(session_factory, fake_embedder, "Digital Lending", [LENDING_PAGE]),
    }


@pytest.fixture
def fake_llm(db_client: AsyncClient) -> FakeProvider:
    provider = FakeProvider()
    app.dependency_overrides[get_provider_factory] = lambda: lambda _name: provider
    app.dependency_overrides[get_settings] = lambda: _settings()
    store = InMemoryConversationStore()
    app.dependency_overrides[get_conversation_store] = lambda: store
    return provider


# --- retrieval --------------------------------------------------------------------------


async def test_retrieval_orders_by_similarity_with_titles_and_pages(
    corpus: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    async with session_factory() as session:
        results = await retrieve(
            session,
            fake_embedder,
            "how long must records of transactions be preserved",
            top_k=3,
            min_score=0.0,
        )

    assert (results[0].document_title, results[0].page_number) == ("KYC Direction", 2)
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


async def test_retrieval_filters_by_document_and_threshold(
    corpus: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    question = "officially valid documents for proof of address"
    async with session_factory() as session:
        only_lending = await retrieve(
            session,
            fake_embedder,
            question,
            top_k=6,
            min_score=0.0,
            document_ids=[corpus["lending"]],
        )
        strict = await retrieve(session, fake_embedder, question, top_k=6, min_score=0.99)

    assert {r.document_id for r in only_lending} == {corpus["lending"]}
    assert strict == []


async def test_retrieval_ignores_documents_that_are_not_ready(
    session_factory: async_sessionmaker[AsyncSession], fake_embedder: FakeEmbeddingProvider
) -> None:
    await _ingest(
        session_factory, fake_embedder, "Draft", [ADDRESS_PAGE], status=DocumentStatus.FAILED
    )
    async with session_factory() as session:
        results = await retrieve(session, fake_embedder, "proof of address", top_k=6, min_score=0)
    assert results == []


# --- /chat --------------------------------------------------------------------------------


async def test_chat_returns_answer_with_page_citations(
    db_client: AsyncClient, corpus: dict[str, uuid.UUID], fake_llm: FakeProvider
) -> None:
    response = await db_client.post(
        "/chat", json={"question": "What documents are valid as proof of address?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "[1]" in body["answer"]
    first = body["citations"][0]
    assert (first["source"], first["document_title"], first["page_number"]) == (
        1,
        "KYC Direction",
        1,
    )
    assert "passport" in first["snippet"].lower()
    assert body["sources"][0]["number"] == 1
    assert body["usage"]["provider"] == "fake"
    assert body["prompt_version"]
    # The model saw the numbered sources in its prompt.
    prompt = fake_llm.calls[0][-1].content
    assert prompt.startswith("Sources:\n[1] KYC Direction, p.1:")


async def test_chat_without_relevant_sources_says_so_without_calling_the_llm(
    db_client: AsyncClient, fake_llm: FakeProvider
) -> None:
    response = await db_client.post("/chat", json={"question": "What is the capital of France?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == NO_ANSWER_TEXT
    assert body["citations"] == [] and body["sources"] == []
    assert fake_llm.calls == []


async def test_chat_keeps_conversation_history(
    db_client: AsyncClient, corpus: dict[str, uuid.UUID], fake_llm: FakeProvider
) -> None:
    first = (await db_client.post("/chat", json={"question": "proof of address documents"})).json()
    await db_client.post(
        "/chat",
        json={"question": "and record retention?", "conversation_id": first["conversation_id"]},
    )

    second_call = fake_llm.calls[1]
    assert [m.role for m in second_call] == ["user", "assistant", "user"]
    assert second_call[0].content == "proof of address documents"
    assert second_call[1].content == first["answer"]


async def test_unconfigured_provider_returns_400(db_client: AsyncClient) -> None:
    def factory(name: str) -> FakeProvider:
        raise ProviderNotConfiguredError(f"Provider '{name}' is not configured")

    app.dependency_overrides[get_provider_factory] = lambda: factory

    response = await db_client.post("/chat", json={"question": "hi", "provider": "anthropic"})
    stream_response = await db_client.post(
        "/chat/stream", json={"question": "hi", "provider": "anthropic"}
    )

    assert response.status_code == stream_response.status_code == 400
    assert "anthropic" in response.json()["detail"]


async def test_unknown_provider_name_is_a_validation_error(db_client: AsyncClient) -> None:
    response = await db_client.post("/chat", json={"question": "hi", "provider": "mistral"})
    assert response.status_code == 422


# --- /chat/stream ---------------------------------------------------------------------


def _parse_sse(raw: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in raw.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_stream_emits_tokens_then_citations_then_done(
    db_client: AsyncClient, corpus: dict[str, uuid.UUID], fake_llm: FakeProvider
) -> None:
    async with db_client.stream(
        "POST", "/chat/stream", json={"question": "valid proof of address documents"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse("".join([chunk async for chunk in response.aiter_text()]))

    names = [name for name, _ in events]
    assert names[-2:] == ["citations", "done"]
    assert set(names[:-2]) == {"token"} and len(names) > 4
    streamed = "".join(str(data["text"]) for name, data in events if name == "token")
    citations_event, done_event = events[-2][1], events[-1][1]
    assert streamed == done_event["answer"]
    assert citations_event["citations"][0]["page_number"] == 1  # type: ignore[index]
    assert done_event["conversation_id"] == citations_event["conversation_id"]


async def test_stream_without_sources_sends_no_answer_text(
    db_client: AsyncClient, fake_llm: FakeProvider
) -> None:
    async with db_client.stream("POST", "/chat/stream", json={"question": "weather?"}) as response:
        events = _parse_sse("".join([chunk async for chunk in response.aiter_text()]))

    assert [name for name, _ in events] == ["token", "citations", "done"]
    assert events[0][1] == {"text": NO_ANSWER_TEXT}
    assert events[1][1]["citations"] == []
