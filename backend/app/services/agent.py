"""Contract review agent: a tool-calling loop over list/search/record/finish tools."""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.llm.base import ChatMessage, LLMProvider
from app.llm.embeddings import EmbeddingProvider
from app.llm.prompts import REVIEW_SYSTEM_PROMPT, build_review_kickoff
from app.models import Document, FindingStatus, Review, ReviewStatus
from app.services.agent_tools import (
    TOOL_SPECS,
    RecordedFinding,
    ReviewToolContext,
    execute_tool,
    save_finding,
)

logger = logging.getLogger(__name__)

MAX_NUDGES = 2


class ReviewProgress:
    """Persists each agent step to the review row so GET /review/{id} shows live progress."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], review_id: uuid.UUID):
        self._session_factory = session_factory
        self._review_id = review_id
        self.steps: list[dict[str, object]] = []
        self.steps_used = 0
        self.tokens_used = 0

    async def add(self, tool: str, description: str, ok: bool = True) -> None:
        self.steps.append(
            {
                "index": len(self.steps) + 1,
                "tool": tool,
                "description": description,
                "ok": ok,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        await self.flush()

    async def flush(self, **fields: object) -> None:
        async with self._session_factory() as session:
            review = await session.get(Review, self._review_id)
            if review is None:
                return
            review.steps = list(self.steps)
            review.steps_used = self.steps_used
            review.tokens_used = self.tokens_used
            for name, value in fields.items():
                setattr(review, name, value)
            await session.commit()


def overall_risk(findings: list[RecordedFinding]) -> str:
    """Conservative: any conflict is high risk; anything unresolved is medium."""
    statuses = {f.status for f in findings}
    if FindingStatus.NON_COMPLIANT in statuses:
        return "high"
    if FindingStatus.NEEDS_REVIEW in statuses:
        return "medium"
    return "low"


def default_summary(findings: list[RecordedFinding]) -> str:
    counts = {s: sum(f.status == s for f in findings) for s in FindingStatus}
    return (
        f"{counts[FindingStatus.NON_COMPLIANT]} clause(s) non-compliant, "
        f"{counts[FindingStatus.NEEDS_REVIEW]} need review and "
        f"{counts[FindingStatus.COMPLIANT]} compliant."
    )


async def run_agent_loop(
    provider: LLMProvider,
    ctx: ReviewToolContext,
    progress: ReviewProgress,
    *,
    contract_title: str,
    max_steps: int,
    timeout_seconds: float,
) -> str | None:
    """Run the model/tool loop. Returns a message if a limit stopped it early, else None."""
    messages = [
        ChatMessage(role="user", content=build_review_kickoff(contract_title, str(ctx.contract_id)))
    ]
    deadline = time.monotonic() + timeout_seconds
    nudges = 0

    for step in range(1, max_steps + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return f"Stopped after the {timeout_seconds:.0f}s time limit."
        try:
            response = await asyncio.wait_for(
                provider.chat_with_tools(messages, TOOL_SPECS, system=REVIEW_SYSTEM_PROMPT),
                timeout=remaining,
            )
        except TimeoutError:
            return f"Stopped after the {timeout_seconds:.0f}s time limit."
        progress.steps_used = step
        progress.tokens_used += response.input_tokens + response.output_tokens
        messages.append(
            ChatMessage(role="assistant", content=response.text, tool_calls=response.tool_calls)
        )

        if not response.tool_calls:
            missing = ctx.unreviewed_clause_ids() if ctx.clauses is not None else ["all clauses"]
            if missing and nudges < MAX_NUDGES:
                nudges += 1
                messages.append(
                    ChatMessage(
                        role="user",
                        content="Continue using the tools. Still without a finding: "
                        f"{', '.join(missing)}. Finish with finish_review.",
                    )
                )
                await progress.add("nudge", "Model paused early; asked it to continue", ok=False)
                continue
            if not ctx.summary and response.text.strip():
                ctx.summary = response.text.strip()
            return None

        for call in response.tool_calls:
            result = await execute_tool(ctx, call)
            messages.append(
                ChatMessage(
                    role="tool", tool_call_id=call.id, name=call.name, content=result.content
                )
            )
            await progress.add(call.name, result.description, ok=result.ok)
        if ctx.finished:
            return None

    return f"Stopped after the maximum of {max_steps} agent steps (MAX_AGENT_STEPS)."


async def fill_missing_findings(ctx: ReviewToolContext, reason: str) -> None:
    for clause in ctx.clauses or []:
        if clause.id not in ctx.findings:
            finding = RecordedFinding(clause, FindingStatus.NEEDS_REVIEW, reason, [])
            ctx.findings[clause.id] = finding
            await save_finding(ctx, finding)


async def run_review_job(
    review_id: uuid.UUID,
    *,
    provider: LLMProvider,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: EmbeddingProvider,
    settings: Settings,
) -> None:
    """Background job: run the agent and store the report. Never raises."""
    progress = ReviewProgress(session_factory, review_id)
    try:
        async with session_factory() as session:
            review = await session.get(Review, review_id)
            contract = await session.get(Document, review.contract_id) if review else None
        if review is None or contract is None:
            return

        ctx = ReviewToolContext(
            review_id=review_id,
            contract_id=contract.id,
            session_factory=session_factory,
            embedder=embedder,
            settings=settings,
        )
        limit_message = await run_agent_loop(
            provider,
            ctx,
            progress,
            contract_title=contract.title,
            max_steps=settings.max_agent_steps,
            timeout_seconds=settings.agent_timeout_seconds,
        )

        unreviewed = ctx.unreviewed_clause_ids()
        if unreviewed:
            await fill_missing_findings(
                ctx, f"Not reviewed by the agent: {limit_message or 'it stopped early'}"
            )
            limit_message = (
                f"{limit_message or 'The agent stopped early.'} {len(unreviewed)} of "
                f"{len(ctx.clauses or [])} clauses were not reviewed and are marked needs_review."
            )

        findings = list(ctx.findings.values())
        await progress.flush(
            status=ReviewStatus.COMPLETED,
            summary=ctx.summary or default_summary(findings),
            overall_risk=overall_risk(findings),
            message=limit_message,
            completed_at=datetime.now(UTC),
        )
    except Exception as exc:
        logger.exception("Review %s failed", review_id)
        await progress.flush(
            status=ReviewStatus.FAILED,
            message=str(exc) or type(exc).__name__,
            completed_at=datetime.now(UTC),
        )
