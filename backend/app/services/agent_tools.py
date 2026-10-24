"""Tools the contract review agent can call, with Pydantic-validated arguments.

Every tool returns a JSON string for the model. Invalid calls return {"error": ...} instead of
raising, so the model can correct itself on the next step.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.llm.base import ToolCall, ToolSpec
from app.llm.embeddings import EmbeddingProvider
from app.models import Chunk, DocType, DocumentPage, Finding
from app.services.citations import make_snippet
from app.services.clauses import Clause, split_clauses
from app.services.pdf import PageText
from app.services.retrieval import RetrievedChunk, retrieve

SOURCE_TEXT_CHARS = 700
CLAUSE_TEXT_CHARS = 2000


# --- argument schemas -----------------------------------------------------------------


class ListContractClausesArgs(BaseModel):
    contract_id: str = Field(description="ID of the contract under review")


class SearchPoliciesArgs(BaseModel):
    query: str = Field(
        min_length=3,
        max_length=500,
        description="What to look for in the policies, e.g. 'retention period for KYC records'",
    )
    top_k: int = Field(default=4, ge=1, le=8, description="Number of passages to return")


class RecordFindingArgs(BaseModel):
    clause_id: str = Field(description="Clause id from list_contract_clauses, e.g. 'c3'")
    status: Literal["compliant", "non_compliant", "needs_review"]
    reason: str = Field(
        min_length=10, max_length=2000, description="One to three sentences explaining why"
    )
    policy_citations: list[str] = Field(
        default_factory=list,
        description="source_id values (e.g. 'S2') from search_policies that support the finding",
    )


class FinishReviewArgs(BaseModel):
    summary: str = Field(
        min_length=20,
        max_length=3000,
        description="2-4 sentence summary for a compliance officer, highlighting the main risks",
    )


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


TOOL_ARGS: dict[str, type[BaseModel]] = {
    "list_contract_clauses": ListContractClausesArgs,
    "search_policies": SearchPoliciesArgs,
    "record_finding": RecordFindingArgs,
    "finish_review": FinishReviewArgs,
}

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_contract_clauses",
        description="List the clauses of the contract under review (id, title, page, text). "
        "Call this first.",
        parameters=_schema(ListContractClausesArgs),
    ),
    ToolSpec(
        name="search_policies",
        description="Semantic search over the stored policy and regulatory documents. Returns "
        "passages with a source_id, document title and page number.",
        parameters=_schema(SearchPoliciesArgs),
    ),
    ToolSpec(
        name="record_finding",
        description="Record the compliance finding for one clause. Calling it again for the "
        "same clause replaces the earlier finding. non_compliant findings must cite at least "
        "one source_id.",
        parameters=_schema(RecordFindingArgs),
    ),
    ToolSpec(
        name="finish_review",
        description="Finish the review once every clause has a finding.",
        parameters=_schema(FinishReviewArgs),
    ),
]


# --- execution context ------------------------------------------------------------------


@dataclass
class ToolResult:
    content: str  # JSON sent back to the model
    ok: bool
    description: str  # short, human-readable progress line for the UI


@dataclass
class RecordedFinding:
    clause: Clause
    status: str
    reason: str
    citations: list[dict[str, Any]]


@dataclass
class ReviewToolContext:
    review_id: uuid.UUID
    contract_id: uuid.UUID
    session_factory: async_sessionmaker[AsyncSession]
    embedder: EmbeddingProvider
    settings: Settings
    clauses: list[Clause] | None = None
    sources: dict[str, RetrievedChunk] = field(default_factory=dict)
    findings: dict[str, RecordedFinding] = field(default_factory=dict)
    summary: str | None = None
    finished: bool = False

    def clause_by_id(self, clause_id: str) -> Clause | None:
        return next((c for c in self.clauses or [] if c.id == clause_id), None)

    def unreviewed_clause_ids(self) -> list[str]:
        return [c.id for c in self.clauses or [] if c.id not in self.findings]

    def source_id_for(self, chunk: RetrievedChunk) -> str:
        for source_id, existing in self.sources.items():
            if existing.chunk_id == chunk.chunk_id:
                return source_id
        source_id = f"S{len(self.sources) + 1}"
        self.sources[source_id] = chunk
        return source_id


def _error(message: str, description: str) -> ToolResult:
    return ToolResult(json.dumps({"error": message}), ok=False, description=description)


def _ok(payload: dict[str, Any], description: str) -> ToolResult:
    return ToolResult(json.dumps(payload, default=str), ok=True, description=description)


# --- tool implementations ---------------------------------------------------------------


async def load_contract_pages(session: AsyncSession, contract_id: uuid.UUID) -> list[PageText]:
    rows = (
        await session.execute(
            select(DocumentPage.page_number, DocumentPage.text)
            .where(DocumentPage.document_id == contract_id)
            .order_by(DocumentPage.page_number)
        )
    ).all()
    if rows:
        return [PageText(page_number=p, text=t) for p, t in rows]
    # Documents ingested before page texts were stored: rebuild pages from chunks.
    chunks = (
        await session.execute(
            select(Chunk.page_number, Chunk.content)
            .where(Chunk.document_id == contract_id)
            .order_by(Chunk.chunk_index)
        )
    ).all()
    pages: dict[int, list[str]] = {}
    for page, content in chunks:
        pages.setdefault(page, []).append(content)
    return [PageText(page_number=p, text="\n".join(parts)) for p, parts in sorted(pages.items())]


async def list_contract_clauses(
    ctx: ReviewToolContext, args: ListContractClausesArgs
) -> ToolResult:
    if args.contract_id != str(ctx.contract_id):
        return _error(
            f"Unknown contract_id. The contract under review is {ctx.contract_id}.",
            "Rejected clause listing for another contract",
        )
    if ctx.clauses is None:
        async with ctx.session_factory() as session:
            pages = await load_contract_pages(session, ctx.contract_id)
        ctx.clauses = split_clauses(pages, max_clauses=ctx.settings.agent_max_clauses)
    clauses = [
        {"id": c.id, "title": c.title, "page": c.page, "text": c.text[:CLAUSE_TEXT_CHARS]}
        for c in ctx.clauses
    ]
    return _ok(
        {"clauses": clauses, "count": len(clauses)},
        f"Read the contract: {len(clauses)} clauses",
    )


async def search_policies(ctx: ReviewToolContext, args: SearchPoliciesArgs) -> ToolResult:
    async with ctx.session_factory() as session:
        chunks = await retrieve(
            session,
            ctx.embedder,
            args.query,
            top_k=args.top_k,
            min_score=ctx.settings.retrieval_min_score,
            doc_types=[DocType.POLICY],
        )
    results = [
        {
            "source_id": ctx.source_id_for(chunk),
            "document_title": chunk.document_title,
            "page": chunk.page_number,
            "score": chunk.score,
            "text": chunk.content[:SOURCE_TEXT_CHARS],
        }
        for chunk in chunks
    ]
    payload: dict[str, Any] = {"results": results}
    if not results:
        payload["note"] = "No policy passage matched. If nothing else applies, use needs_review."
    return _ok(payload, f"Searched policies for: {args.query[:120]}")


async def record_finding(ctx: ReviewToolContext, args: RecordFindingArgs) -> ToolResult:
    if ctx.clauses is None:
        return _error("Call list_contract_clauses first.", "Rejected finding: clauses not listed")
    clause = ctx.clause_by_id(args.clause_id)
    if clause is None:
        valid = ", ".join(c.id for c in ctx.clauses)
        return _error(
            f"Unknown clause_id '{args.clause_id}'. Valid ids: {valid}.",
            f"Rejected finding for unknown clause {args.clause_id}",
        )
    unknown = [s for s in args.policy_citations if s not in ctx.sources]
    if unknown:
        return _error(
            f"Unknown source_id(s) {unknown}. Only cite source_id values returned by "
            "search_policies.",
            f"Rejected finding for {clause.id}: invalid citations",
        )
    if args.status == "non_compliant" and not args.policy_citations:
        return _error(
            "A non_compliant finding must cite at least one policy source_id.",
            f"Rejected finding for {clause.id}: no citation",
        )

    citations = [
        {
            "source_id": source_id,
            "document_id": str(ctx.sources[source_id].document_id),
            "document_title": ctx.sources[source_id].document_title,
            "page_number": ctx.sources[source_id].page_number,
            "snippet": make_snippet(
                ctx.sources[source_id].content, ctx.settings.citation_snippet_chars
            ),
        }
        for source_id in dict.fromkeys(args.policy_citations)
    ]
    finding = RecordedFinding(clause, args.status, args.reason, citations)
    ctx.findings[clause.id] = finding
    await save_finding(ctx, finding)
    label = args.status.replace("_", "-")
    return _ok(
        {"recorded": clause.id, "remaining": ctx.unreviewed_clause_ids()},
        f"{clause.id} {clause.title}: {label}",
    )


async def finish_review(ctx: ReviewToolContext, args: FinishReviewArgs) -> ToolResult:
    missing = ctx.unreviewed_clause_ids() if ctx.clauses is not None else ["(clauses not listed)"]
    if missing:
        return _error(
            f"These clauses still need a finding: {', '.join(missing)}.",
            "Finish rejected: some clauses have no finding",
        )
    ctx.summary = args.summary
    ctx.finished = True
    return _ok({"finished": True}, "Wrote the summary")


async def save_finding(ctx: ReviewToolContext, finding: RecordedFinding) -> None:
    """Upsert so the UI sees findings live and a repeated call replaces the earlier one."""
    position = next(i for i, c in enumerate(ctx.clauses or []) if c.id == finding.clause.id)
    values = {
        "review_id": ctx.review_id,
        "position": position,
        "clause_id": finding.clause.id,
        "clause_title": finding.clause.title[:300],
        "clause_page": finding.clause.page,
        "status": finding.status,
        "reason": finding.reason,
        "policy_citations": finding.citations,
    }
    statement = insert(Finding).values(id=uuid.uuid4(), **values)
    statement = statement.on_conflict_do_update(
        constraint="uq_findings_review_clause",
        set_={k: statement.excluded[k] for k in ("status", "reason", "policy_citations")},
    )
    async with ctx.session_factory() as session:
        await session.execute(statement)
        await session.commit()


ToolFn = Callable[[ReviewToolContext, Any], Awaitable[ToolResult]]
TOOL_FUNCTIONS: dict[str, ToolFn] = {
    "list_contract_clauses": list_contract_clauses,
    "search_policies": search_policies,
    "record_finding": record_finding,
    "finish_review": finish_review,
}


async def execute_tool(ctx: ReviewToolContext, call: ToolCall) -> ToolResult:
    """Validate and run one tool call. Never raises for bad model input."""
    if call.name not in TOOL_FUNCTIONS:
        return _error(
            f"Unknown tool '{call.name}'. Available tools: {', '.join(TOOL_FUNCTIONS)}.",
            f"Rejected unknown tool {call.name}",
        )
    if "__invalid_json__" in call.arguments:
        return _error("Arguments were not valid JSON.", f"Rejected {call.name}: invalid JSON")
    try:
        args = TOOL_ARGS[call.name].model_validate(call.arguments)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
        )
        return _error(f"Invalid arguments: {problems}", f"Rejected {call.name}: invalid arguments")
    return await TOOL_FUNCTIONS[call.name](ctx, args)
