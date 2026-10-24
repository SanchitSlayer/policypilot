import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import get_db_session, get_sessionmaker
from app.llm.embeddings import EmbeddingError, EmbeddingProvider, get_embedding_provider
from app.models import DocType
from app.schemas.document import DocumentDetail, DocumentOut
from app.services import documents as document_service
from app.services.ingestion import ingest_document
from app.services.pdf import is_pdf

router = APIRouter(prefix="/documents", tags=["documents"])

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_embedder() -> EmbeddingProvider:
    try:
        return get_embedding_provider()
    except EmbeddingError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory for background work that outlives the request session."""
    return get_sessionmaker()


async def read_pdf_upload(file: UploadFile, max_bytes: int) -> bytes:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PDF files (.pdf) are accepted."
        )
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {max_bytes / (1024 * 1024):.0f} MB upload limit.",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")
    if not is_pdf(data):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file does not look like a PDF (missing %PDF header).",
        )
    return data


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    embedder: Annotated[EmbeddingProvider, Depends(get_embedder)],
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    file: Annotated[UploadFile, File(description="PDF file")],
    doc_type: Annotated[DocType, Form()] = DocType.POLICY,
    title: Annotated[str | None, Form(max_length=500)] = None,
) -> DocumentOut:
    """Upload a PDF. Returns at once with status "processing"; ingestion runs in the background."""
    data = await read_pdf_upload(file, settings.max_upload_bytes)
    document = await document_service.create_document(
        session, filename=file.filename or "document.pdf", title=title, doc_type=doc_type
    )
    background_tasks.add_task(
        ingest_document,
        document.id,
        data,
        session_factory=session_factory,
        embedder=embedder,
        settings=settings,
    )
    return DocumentOut.model_validate(document)


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: SessionDep) -> list[DocumentOut]:
    return await document_service.list_documents(session)


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentDetail:
    detail = await document_service.get_document_detail(session, document_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return detail


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, session: SessionDep) -> Response:
    if not await document_service.delete_document(session, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
