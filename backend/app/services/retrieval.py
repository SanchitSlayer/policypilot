"""Vector search over chunks with pgvector cosine distance."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.embeddings import EmbeddingProvider
from app.models import Chunk, DocType, Document, DocumentStatus


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int
    content: str
    score: float  # cosine similarity, 1.0 = identical direction


async def retrieve(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    query: str,
    *,
    top_k: int,
    min_score: float,
    document_ids: Sequence[uuid.UUID] | None = None,
    doc_types: Sequence[DocType] | None = None,
) -> list[RetrievedChunk]:
    """Return up to `top_k` chunks from ready documents, most similar first, dropping any
    whose similarity is below `min_score`."""
    [query_vector] = await embedder.embed([query])
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    statement = (
        select(
            Chunk.id,
            Chunk.document_id,
            Document.title,
            Chunk.page_number,
            Chunk.content,
            distance,
        )
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.status == DocumentStatus.READY)
        .order_by(distance)
        .limit(top_k)
    )
    if document_ids:
        statement = statement.where(Chunk.document_id.in_(list(document_ids)))
    if doc_types:
        statement = statement.where(Document.doc_type.in_([str(t) for t in doc_types]))

    rows = (await session.execute(statement)).all()
    results = [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            page_number=row.page_number,
            content=row.content,
            score=round(1.0 - float(row.distance), 4),
        )
        for row in rows
    ]
    return [r for r in results if r.score >= min_score]
