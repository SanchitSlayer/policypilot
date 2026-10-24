"""Ingest every PDF in a folder: `python -m app.scripts.ingest_folder sample_data/`."""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import close_connections, get_mongo_db, get_sessionmaker
from app.llm.embeddings import EmbeddingError, get_embedding_provider
from app.llm.pricing import get_pricing
from app.llm.usage import LoggedEmbeddingProvider, MongoUsageLogger
from app.models import DocType, Document, DocumentStatus
from app.services.documents import create_document
from app.services.ingestion import ingest_document
from app.services.pdf import is_pdf


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder containing PDF files")
    parser.add_argument(
        "--doc-type",
        choices=[t.value for t in DocType],
        default=DocType.POLICY.value,
        help="Type to assign to every ingested file (default: policy)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ingest files again even if a ready document with the same filename exists",
    )
    return parser.parse_args(argv)


async def already_ingested(filename: str) -> bool:
    async with get_sessionmaker()() as session:
        existing = await session.scalar(
            select(Document.id).where(
                Document.filename == filename, Document.status == DocumentStatus.READY
            )
        )
        return existing is not None


async def ingest_file(path: Path, doc_type: DocType, force: bool) -> str:
    data = await asyncio.to_thread(path.read_bytes)
    if not is_pdf(data):
        return "skipped (not a PDF)"
    if not force and await already_ingested(path.name):
        return "skipped (already ingested)"

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        document = await create_document(session, filename=path.name, title=None, doc_type=doc_type)
    await ingest_document(
        document.id,
        data,
        session_factory=session_factory,
        embedder=LoggedEmbeddingProvider(
            get_embedding_provider(),
            usage_logger=MongoUsageLogger(get_mongo_db()),
            pricing=get_pricing(),
        ),
        settings=get_settings(),
    )
    async with session_factory() as session:
        refreshed = await session.get(Document, document.id)
    assert refreshed is not None
    if refreshed.status == DocumentStatus.READY:
        return f"ready ({refreshed.num_pages} pages)"
    return f"failed: {refreshed.error_message}"


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}", file=sys.stderr)
        return 2
    try:
        get_embedding_provider()
    except EmbeddingError as exc:
        print(f"Embedding provider error: {exc}", file=sys.stderr)
        return 2

    pdfs = sorted(p for p in args.folder.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"No PDF files found in {args.folder}")
        return 0

    failures = 0
    try:
        for path in pdfs:
            result = await ingest_file(path, DocType(args.doc_type), args.force)
            failures += result.startswith("failed")
            print(f"{path.name}: {result}")
    finally:
        await close_connections()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
