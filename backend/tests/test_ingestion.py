"""End-to-end ingestion against a real Postgres + pgvector (FakeEmbeddingProvider, no network)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.llm.embeddings import FakeEmbeddingProvider
from app.main import app
from app.models import Chunk, Document, DocumentStatus
from app.services.ingestion import ingest_document
from tests.pdf_factory import make_pdf

KYC_PAGE = (
    "Customer Due Diligence. Regulated entities shall verify the identity of every customer "
    "using an officially valid document such as a passport, driving licence or Aadhaar. "
) * 6
RECORDS_PAGE = "Record keeping. Records of transactions shall be preserved for five years. " * 6


async def test_upload_ingests_pdf_into_page_numbered_chunks(
    db_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"chunk_size_tokens": 60, "chunk_overlap_tokens": 10}
    )
    pdf = make_pdf([KYC_PAGE, "", RECORDS_PAGE])

    response = await db_client.post(
        "/documents",
        files={"file": ("rbi_kyc_master_direction.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "processing"
    assert created["title"] == "rbi kyc master direction"

    # httpx's ASGI transport waits for background tasks, so ingestion has finished.
    detail = (await db_client.get(f"/documents/{created['id']}")).json()
    assert detail["status"] == "ready", detail["error_message"]
    assert detail["num_pages"] == 3
    pages = {c["page_number"] for c in detail["chunks"]}
    assert pages == {1, 3}, "blank page 2 must be skipped"
    assert detail["chunk_count"] == len(detail["chunks"]) > 2
    assert all(c["token_count"] <= 60 for c in detail["chunks"])
    assert any("five years" in c["content"] for c in detail["chunks"] if c["page_number"] == 3)

    listed = (await db_client.get("/documents")).json()
    assert [(d["id"], d["chunk_count"]) for d in listed] == [(created["id"], len(detail["chunks"]))]

    async with session_factory() as session:
        embedding = await session.scalar(select(Chunk.embedding).limit(1))
    assert embedding is not None and len(embedding) == get_settings().embedding_dim


async def test_embeddings_support_cosine_search(
    session_factory: async_sessionmaker[AsyncSession], fake_embedder: FakeEmbeddingProvider
) -> None:
    document_id = await _create_document(session_factory)
    await ingest_document(
        document_id,
        make_pdf([KYC_PAGE, RECORDS_PAGE]),
        session_factory=session_factory,
        embedder=fake_embedder,
        settings=get_settings(),
    )

    query = fake_embedder.embed_one("how long must transaction records be preserved")
    async with session_factory() as session:
        best_page = await session.scalar(
            select(Chunk.page_number).order_by(Chunk.embedding.cosine_distance(query)).limit(1)
        )
    assert best_page == 2


async def test_pdf_without_text_is_marked_failed(
    session_factory: async_sessionmaker[AsyncSession], fake_embedder: FakeEmbeddingProvider
) -> None:
    document_id = await _create_document(session_factory)

    await ingest_document(
        document_id,
        make_pdf(["", ""]),
        session_factory=session_factory,
        embedder=fake_embedder,
        settings=get_settings(),
    )

    async with session_factory() as session:
        document = await session.get(Document, document_id)
    assert document is not None
    assert document.status == DocumentStatus.FAILED
    assert "No extractable text" in (document.error_message or "")


async def test_delete_removes_document_and_its_chunks(
    db_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    created = (
        await db_client.post(
            "/documents", files={"file": ("p.pdf", make_pdf([KYC_PAGE]), "application/pdf")}
        )
    ).json()

    assert (await db_client.delete(f"/documents/{created['id']}")).status_code == 204
    assert (await db_client.get(f"/documents/{created['id']}")).status_code == 404
    assert (await db_client.delete(f"/documents/{created['id']}")).status_code == 404
    async with session_factory() as session:
        assert await session.scalar(select(func.count(Chunk.id))) == 0


async def _create_document(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session:
        document = Document(filename="t.pdf", title="Test", status=DocumentStatus.PROCESSING)
        session.add(document)
        await session.commit()
        return document.id
