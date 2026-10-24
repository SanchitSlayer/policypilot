"""Contract review agent: scripted FakeProvider runs against real Postgres + pgvector."""

import asyncio
import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_provider_factory
from app.core.config import Settings, get_settings
from app.llm.base import ChatMessage, LLMResponse, ProviderNotConfiguredError, ToolCall
from app.llm.embeddings import FakeEmbeddingProvider
from app.llm.fake_provider import FakeProvider
from app.main import app
from app.models import DocType, Document, DocumentStatus, Finding, Review, ReviewStatus
from app.scripts.make_sample_data import CONTRACT, POLICY
from app.services.agent import overall_risk, run_review_job
from app.services.agent_tools import RecordedFinding
from app.services.clauses import Clause
from app.services.ingestion import ingest_document
from app.utils.simple_pdf import make_text_pdf

NUM_CLAUSES = 11  # in the sample contract


def _settings(**overrides: Any) -> Settings:
    base = {"retrieval_min_score": 0.0, "default_llm_provider": "fake"}
    return get_settings().model_copy(update={**base, **overrides})


def step(*calls: tuple[str, dict[str, Any]], text: str = "") -> LLMResponse:
    """One scripted model turn making the given (tool name, arguments) calls."""
    return LLMResponse(
        text=text,
        input_tokens=100,
        output_tokens=20,
        model="scripted",
        provider="fake",
        tool_calls=[
            ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=args)
            for name, args in calls
        ],
    )


async def _ingest(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: FakeEmbeddingProvider,
    title: str,
    text: str,
    doc_type: DocType,
) -> uuid.UUID:
    async with session_factory() as session:
        doc = Document(
            filename=f"{title}.pdf",
            title=title,
            doc_type=doc_type,
            status=DocumentStatus.PROCESSING,
        )
        session.add(doc)
        await session.commit()
        doc_id = doc.id
    await ingest_document(
        doc_id,
        make_text_pdf(text),
        session_factory=session_factory,
        embedder=embedder,
        settings=get_settings(),
    )
    return doc_id


@pytest.fixture
async def docs(
    session_factory: async_sessionmaker[AsyncSession], fake_embedder: FakeEmbeddingProvider
) -> dict[str, uuid.UUID]:
    return {
        "policy": await _ingest(
            session_factory, fake_embedder, "Internal KYC Policy", POLICY, DocType.POLICY
        ),
        "contract": await _ingest(
            session_factory, fake_embedder, "Vendor Agreement", CONTRACT, DocType.CONTRACT
        ),
    }


async def _run(
    provider: FakeProvider,
    contract_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: FakeEmbeddingProvider,
    **settings: Any,
) -> tuple[Review, list[Finding]]:
    async with session_factory() as session:
        review = Review(
            contract_id=contract_id, provider="fake", status=ReviewStatus.RUNNING, steps=[]
        )
        session.add(review)
        await session.commit()
        review_id = review.id
    await run_review_job(
        review_id,
        provider=provider,
        session_factory=session_factory,
        embedder=embedder,
        settings=_settings(**settings),
    )
    async with session_factory() as session:
        review = await session.get(Review, review_id)
        findings = (
            await session.scalars(
                select(Finding).where(Finding.review_id == review_id).order_by(Finding.position)
            )
        ).all()
    assert review is not None
    return review, list(findings)


def _tool_messages(provider: FakeProvider) -> list[ChatMessage]:
    return [m for m in provider.calls[-1] if m.role == "tool"]


# --- the loop -----------------------------------------------------------------------------


async def test_agent_records_a_finding_per_clause_and_finishes(
    docs: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    cid = str(docs["contract"])
    records = [
        (
            "record_finding",
            {"clause_id": f"c{n}", "status": "compliant", "reason": "No policy issue here."},
        )
        for n in range(1, NUM_CLAUSES + 1)
        if n != 5
    ]
    provider = FakeProvider(
        script=[
            step(("list_contract_clauses", {"contract_id": cid})),
            step(("search_policies", {"query": "how long must KYC records be preserved"})),
            step(
                (
                    "record_finding",
                    {
                        "clause_id": "c5",
                        "status": "non_compliant",
                        "reason": "Deletes records after 12 months; policy requires five years.",
                        "policy_citations": ["S1"],
                    },
                ),
                *records,
            ),
            step(("finish_review", {"summary": "Retention clause breaches the five-year rule."})),
        ]
    )

    review, findings = await _run(provider, docs["contract"], session_factory, fake_embedder)

    assert review.status == ReviewStatus.COMPLETED
    assert review.message is None
    assert review.summary == "Retention clause breaches the five-year rule."
    assert review.overall_risk == "high"
    assert (review.steps_used, review.tokens_used) == (4, 480)
    assert len(findings) == NUM_CLAUSES
    retention = next(f for f in findings if f.clause_id == "c5")
    assert retention.status == "non_compliant"
    assert retention.clause_title == "5. Data retention and deletion"
    assert retention.policy_citations[0]["document_title"] == "Internal KYC Policy"
    assert retention.policy_citations[0]["source_id"] == "S1"
    descriptions = [s["description"] for s in review.steps]
    assert descriptions[0] == f"Read the contract: {NUM_CLAUSES} clauses"
    assert descriptions[1].startswith("Searched policies for:")
    assert all(s["ok"] for s in review.steps)


async def test_agent_stops_at_max_steps_and_marks_the_rest_needs_review(
    docs: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    cid = str(docs["contract"])
    provider = FakeProvider(
        script=[step(("list_contract_clauses", {"contract_id": cid}))]
        + [step(("search_policies", {"query": f"query number {n}"})) for n in range(10)]
    )

    review, findings = await _run(
        provider, docs["contract"], session_factory, fake_embedder, max_agent_steps=3
    )

    assert review.status == ReviewStatus.COMPLETED
    assert review.steps_used == 3
    assert "maximum of 3 agent steps" in (review.message or "")
    assert f"{NUM_CLAUSES} of {NUM_CLAUSES} clauses were not reviewed" in (review.message or "")
    assert len(findings) == NUM_CLAUSES
    assert {f.status for f in findings} == {"needs_review"}
    assert findings[0].reason.startswith("Not reviewed by the agent")
    assert review.overall_risk == "medium"


async def test_invalid_tool_calls_return_errors_and_the_loop_continues(
    docs: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    cid = str(docs["contract"])
    bad_calls = [
        ("delete_all_records", {}),
        ("record_finding", {"clause_id": "c1", "status": "compliant", "reason": "Too early call."}),
        ("list_contract_clauses", {"contract_id": str(uuid.uuid4())}),
        ("search_policies", {"query": "x"}),  # too short
        ("search_policies", {"__invalid_json__": "{oops"}),
    ]
    after_listing = [
        (
            "record_finding",
            {"clause_id": "c99", "status": "compliant", "reason": "No such clause."},
        ),
        ("record_finding", {"clause_id": "c1", "status": "maybe", "reason": "Invalid status."}),
        (
            "record_finding",
            {"clause_id": "c5", "status": "non_compliant", "reason": "Missing cite."},
        ),
        (
            "record_finding",
            {
                "clause_id": "c5",
                "status": "needs_review",
                "reason": "Cites a source that was never returned.",
                "policy_citations": ["S99"],
            },
        ),
        ("finish_review", {"summary": "Finishing before every clause has a finding."}),
    ]
    provider = FakeProvider(
        script=[
            step(*bad_calls),
            step(("list_contract_clauses", {"contract_id": cid})),
            step(*after_listing),
            step(text="Done."),  # stops without finishing -> nudged
            step(text="Done."),
            step(text="Done."),
        ]
    )

    review, findings = await _run(provider, docs["contract"], session_factory, fake_embedder)

    oks = [s["ok"] for s in review.steps if s["tool"] != "nudge"]
    assert oks == [False] * 5 + [True] + [False] * 5
    errors = [json.loads(m.content).get("error", "") for m in _tool_messages(provider)]
    assert "Unknown tool 'delete_all_records'" in errors[0]
    assert "Call list_contract_clauses first" in errors[1]
    assert "Unknown contract_id" in errors[2]
    assert "query" in errors[3] and "at least 3 characters" in errors[3]
    assert "not valid JSON" in errors[4]
    assert "Valid ids: c1, c2" in errors[6]
    assert "status" in errors[7]
    assert "must cite at least one" in errors[8]
    assert "Unknown source_id(s) ['S99']" in errors[9]
    assert "still need a finding" in errors[10]
    # The model stopped twice without finishing: nudged twice, then the loop ended.
    assert [s["tool"] for s in review.steps].count("nudge") == 2
    assert review.steps_used == 6
    assert len(findings) == NUM_CLAUSES and {f.status for f in findings} == {"needs_review"}


async def test_agent_stops_at_the_time_limit(
    docs: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    class SlowProvider(FakeProvider):
        async def chat_with_tools(self, *args: Any, **kwargs: Any) -> LLMResponse:
            await asyncio.sleep(1)
            raise AssertionError("should have timed out")

    review, findings = await _run(
        SlowProvider(), docs["contract"], session_factory, fake_embedder, agent_timeout_seconds=0.05
    )

    assert review.status == ReviewStatus.COMPLETED
    assert "time limit" in (review.message or "")
    assert findings == []  # the clauses were never listed


async def test_provider_error_marks_the_review_failed(
    docs: dict[str, uuid.UUID],
    session_factory: async_sessionmaker[AsyncSession],
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    review, _ = await _run(
        FakeProvider(script=[]), docs["contract"], session_factory, fake_embedder
    )

    assert review.status == ReviewStatus.FAILED
    assert review.message == "FakeProvider script exhausted"


def test_overall_risk_is_conservative() -> None:
    clause = Clause("c1", "t", "x", 1)
    finding = lambda status: RecordedFinding(clause, status, "r", [])  # noqa: E731
    assert overall_risk([finding("compliant")]) == "low"
    assert overall_risk([finding("compliant"), finding("needs_review")]) == "medium"
    assert overall_risk([finding("needs_review"), finding("non_compliant")]) == "high"


# --- API ------------------------------------------------------------------------------


@pytest.fixture
def review_client(db_client: AsyncClient) -> AsyncClient:
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_provider_factory] = lambda: lambda _name: FakeProvider()
    return db_client


async def test_review_api_runs_the_offline_agent_end_to_end(
    review_client: AsyncClient, docs: dict[str, uuid.UUID]
) -> None:
    created = await review_client.post(
        "/review", json={"document_id": str(docs["contract"]), "provider": "fake"}
    )
    assert created.status_code == 202

    body = (await review_client.get(f"/review/{created.json()['review_id']}")).json()

    assert body["status"] == "completed"
    assert body["contract_title"] == "Vendor Agreement"
    assert [s["tool"] for s in body["steps"]][:2] == ["list_contract_clauses", "search_policies"]
    report = body["report"]
    assert report["overall_risk"] == "medium"
    assert report["steps_used"] == 4
    assert len(report["findings"]) == NUM_CLAUSES
    assert report["findings"][0]["clause_title"] == "1. Parties and effective date"
    assert report["findings"][0]["policy_citations"][0]["document_title"] == "Internal KYC Policy"
    assert report["summary"].startswith("Offline demo review of 11 clauses")


async def test_review_api_validates_the_request(
    review_client: AsyncClient, docs: dict[str, uuid.UUID]
) -> None:
    not_contract = await review_client.post("/review", json={"document_id": str(docs["policy"])})
    missing = await review_client.post("/review", json={"document_id": str(uuid.uuid4())})
    no_review = await review_client.get(f"/review/{uuid.uuid4()}")

    def unconfigured(name: str) -> FakeProvider:
        raise ProviderNotConfiguredError(f"Provider '{name}' is not configured")

    app.dependency_overrides[get_provider_factory] = lambda: unconfigured
    no_key = await review_client.post(
        "/review", json={"document_id": str(docs["contract"]), "provider": "openai"}
    )

    assert not_contract.status_code == 422
    assert "contract" in not_contract.json()["detail"]
    assert missing.status_code == 404
    assert no_review.status_code == 404
    assert no_key.status_code == 400
