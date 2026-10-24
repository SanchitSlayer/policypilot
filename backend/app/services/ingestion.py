"""Ingestion pipeline: PDF bytes -> page texts -> token chunks -> embeddings -> pgvector."""

import asyncio
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.llm.embeddings import EmbeddingProvider
from app.models import Chunk, Document, DocumentStatus
from app.services.chunking import TextChunk, chunk_pages
from app.services.pdf import extract_pages

logger = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    """A user-facing reason why a document could not be ingested."""


async def embed_in_batches(
    embedder: EmbeddingProvider, texts: Sequence[str], batch_size: int
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = list(texts[start : start + batch_size])
        batch_vectors = await embedder.embed(batch)
        if len(batch_vectors) != len(batch):
            raise IngestionError(
                f"Embedding provider returned {len(batch_vectors)} vectors for {len(batch)} texts."
            )
        vectors.extend(batch_vectors)
    return vectors


async def build_chunks(
    pdf_bytes: bytes, embedder: EmbeddingProvider, settings: Settings
) -> tuple[int, list[TextChunk], list[list[float]]]:
    num_pages, pages = await asyncio.to_thread(extract_pages, pdf_bytes)
    if not pages:
        raise IngestionError(
            "No extractable text found. The PDF may be scanned images (OCR is not supported yet)."
        )
    chunks = chunk_pages(
        pages,
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
        encoding_name=settings.tokenizer_encoding,
    )
    vectors = await embed_in_batches(
        embedder, [c.content for c in chunks], settings.embedding_batch_size
    )
    return num_pages, chunks, vectors


async def ingest_document(
    document_id: uuid.UUID,
    pdf_bytes: bytes,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: EmbeddingProvider,
    settings: Settings,
) -> None:
    """Process one uploaded PDF and mark the document ready or failed. Never raises."""
    try:
        num_pages, chunks, vectors = await build_chunks(pdf_bytes, embedder, settings)
        async with session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:  # deleted while processing
                return
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            session.add_all(
                Chunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=vector,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            )
            document.num_pages = num_pages
            document.status = DocumentStatus.READY
            document.error_message = None
            await session.commit()
        logger.info("Ingested document %s: %d chunks", document_id, len(chunks))
    except Exception as exc:
        logger.exception("Ingestion failed for document %s", document_id)
        await _mark_failed(session_factory, document_id, str(exc) or type(exc).__name__)


async def _mark_failed(
    session_factory: async_sessionmaker[AsyncSession], document_id: uuid.UUID, message: str
) -> None:
    async with session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = DocumentStatus.FAILED
        document.error_message = message[:2000]
        await session.commit()
