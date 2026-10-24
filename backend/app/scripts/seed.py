"""Load the demo corpus so a fresh install is ready to use: `python -m app.scripts.seed`.

Writes the fictional sample PDFs if they are missing, then ingests every PDF in the sample
folder. Files whose names contain "agreement" or "contract" are ingested as contracts; all
others as policies. Already-ingested files are skipped unless --force is given (use --force
after changing EMBEDDING_PROVIDER, since embeddings from different models do not mix).
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import close_connections, get_sessionmaker
from app.llm.embeddings import EmbeddingError, EmbeddingProvider
from app.models import DocType
from app.scripts.ingest_folder import ingest_file, logged_embedder
from app.scripts.make_sample_data import DEFAULT_DIR, POLICIES, write_samples

CONTRACT_MARKERS = ("agreement", "contract")


def doc_type_for(path: Path) -> DocType:
    name = path.name.lower()
    return DocType.CONTRACT if any(m in name for m in CONTRACT_MARKERS) else DocType.POLICY


def _prepare_folder(folder: Path) -> list[Path]:
    """Write the sample PDFs if any are missing; return the PDFs to ingest."""
    if not all((folder / name).exists() for name in POLICIES):
        write_samples(folder)
    return sorted(folder.glob("*.pdf"))


async def seed_folder(
    folder: Path,
    *,
    force: bool,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: EmbeddingProvider,
) -> dict[str, str]:
    results = {}
    for path in await asyncio.to_thread(_prepare_folder, folder):
        results[path.name] = await ingest_file(
            path,
            doc_type_for(path),
            force=force,
            session_factory=session_factory,
            embedder=embedder,
        )
    return results


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder", type=Path, default=Path(os.getenv("SAMPLE_DATA_DIR", DEFAULT_DIR))
    )
    parser.add_argument("--force", action="store_true", help="Re-ingest files already loaded")
    args = parser.parse_args(argv)

    try:
        embedder = logged_embedder()
    except EmbeddingError as exc:
        print(f"Embedding provider error: {exc}", file=sys.stderr)
        return 2
    try:
        results = await seed_folder(
            args.folder, force=args.force, session_factory=get_sessionmaker(), embedder=embedder
        )
    finally:
        await close_connections()

    for name, result in results.items():
        print(f"{doc_type_for(Path(name)).value:8} {name}: {result}")
    return 1 if any(r.startswith("failed") for r in results.values()) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
