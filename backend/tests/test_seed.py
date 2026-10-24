"""Seeding the demo corpus into the test database."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.embeddings import FakeEmbeddingProvider
from app.models import Document, DocumentPage
from app.scripts.make_sample_data import KYC_POLICY_PAGES
from app.scripts.seed import doc_type_for, seed_folder


def test_doc_type_comes_from_the_filename() -> None:
    assert doc_type_for(Path("sample_vendor_kyc_agreement.pdf")) == "contract"
    assert doc_type_for(Path("Master_Services_CONTRACT.pdf")) == "contract"
    assert doc_type_for(Path("rbi_kyc_direction.pdf")) == "policy"


async def test_seed_writes_samples_ingests_them_and_is_idempotent(
    tmp_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    first = await seed_folder(
        tmp_path, force=False, session_factory=session_factory, embedder=fake_embedder
    )
    second = await seed_folder(
        tmp_path, force=False, session_factory=session_factory, embedder=fake_embedder
    )

    assert first == {
        "sample_digital_lending_policy.pdf": "ready (4 pages)",
        "sample_information_security_standard.pdf": "ready (3 pages)",
        "sample_internal_kyc_data_policy.pdf": "ready (5 pages)",
        "sample_vendor_kyc_agreement.pdf": "ready (1 pages)",
    }
    assert set(second.values()) == {"skipped (already ingested)"}

    async with session_factory() as session:
        docs = {d.filename: d for d in (await session.scalars(select(Document))).all()}
        kyc_pages = (
            await session.scalars(
                select(DocumentPage.text)
                .where(DocumentPage.document_id == docs["sample_internal_kyc_data_policy.pdf"].id)
                .order_by(DocumentPage.page_number)
            )
        ).all()
    assert docs["sample_vendor_kyc_agreement.pdf"].doc_type == "contract"
    assert {d.doc_type for n, d in docs.items() if "policy" in n or "standard" in n} == {"policy"}
    # Each policy page lands on the PDF page the eval test set expects.
    assert "11. Record retention" in kyc_pages[3] and "11. Record retention" in KYC_POLICY_PAGES[3]
