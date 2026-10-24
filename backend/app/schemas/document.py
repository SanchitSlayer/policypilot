import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import DocType, DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    title: str
    doc_type: DocType
    num_pages: int | None
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
    chunk_count: int = 0


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int
    token_count: int
    content: str


class DocumentDetail(DocumentOut):
    chunks: list[ChunkOut] = []
