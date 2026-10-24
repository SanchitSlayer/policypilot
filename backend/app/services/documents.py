"""Document persistence helpers shared by the API and the CLI."""

import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, DocType, Document, DocumentStatus
from app.schemas.document import ChunkOut, DocumentDetail, DocumentOut


def default_title(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(stem.split()) or "Untitled document"


async def create_document(
    session: AsyncSession, *, filename: str, title: str | None, doc_type: DocType
) -> Document:
    document = Document(
        filename=filename,
        title=(title or "").strip() or default_title(filename),
        doc_type=doc_type,
        status=DocumentStatus.PROCESSING,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def list_documents(session: AsyncSession) -> list[DocumentOut]:
    chunk_count = (
        select(func.count(Chunk.id))
        .where(Chunk.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Document, chunk_count.label("chunk_count")).order_by(Document.created_at.desc())
    )
    return [
        DocumentOut.model_validate(doc).model_copy(update={"chunk_count": count})
        for doc, count in rows.all()
    ]


async def get_document_detail(
    session: AsyncSession, document_id: uuid.UUID
) -> DocumentDetail | None:
    document = await session.get(Document, document_id)
    if document is None:
        return None
    chunks = (
        await session.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
    ).all()
    base = DocumentOut.model_validate(document).model_dump()
    return DocumentDetail(
        **{**base, "chunk_count": len(chunks)},
        chunks=[ChunkOut.model_validate(c) for c in chunks],
    )


async def delete_document(session: AsyncSession, document_id: uuid.UUID) -> bool:
    document = await session.get(Document, document_id)
    if document is None:
        return False
    await session.delete(document)
    await session.commit()
    return True
