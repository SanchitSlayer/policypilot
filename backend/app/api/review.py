import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.chat import get_provider_factory
from app.api.deps import EmbedderDep, SessionDep, SessionFactoryDep, SettingsDep
from app.llm.base import LLMProvider, ProviderNotConfiguredError
from app.llm.prompts import REVIEW_PROMPT_VERSION
from app.models import DocType, Document, DocumentStatus, Review, ReviewStatus
from app.schemas.review import (
    FindingOut,
    ReviewCreated,
    ReviewOut,
    ReviewReport,
    ReviewRequest,
    ReviewStep,
)
from app.services.agent import run_review_job

router = APIRouter(prefix="/review", tags=["contract review"])

ProviderFactoryDep = Annotated[Callable[[str], LLMProvider], Depends(get_provider_factory)]


@router.post("", response_model=ReviewCreated, status_code=status.HTTP_202_ACCEPTED)
async def start_review(
    request: ReviewRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    provider_factory: ProviderFactoryDep,
) -> ReviewCreated:
    """Start a contract review job; poll GET /review/{review_id} for progress and the report."""
    contract = await session.get(Document, request.document_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if contract.doc_type != DocType.CONTRACT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only documents uploaded with type 'contract' can be reviewed.",
        )
    if contract.status != DocumentStatus.READY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"The contract is not ready yet (status: {contract.status}).",
        )
    try:
        provider = provider_factory(request.provider or settings.default_llm_provider)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    review = Review(
        contract_id=contract.id,
        provider=provider.name,
        model=provider.model,
        status=ReviewStatus.RUNNING,
        steps=[],
        prompt_version=REVIEW_PROMPT_VERSION,
    )
    session.add(review)
    await session.commit()

    background_tasks.add_task(
        run_review_job,
        review.id,
        provider=provider,
        session_factory=session_factory,
        embedder=embedder,
        settings=settings,
    )
    return ReviewCreated(review_id=review.id, status=ReviewStatus.RUNNING)


@router.get("/{review_id}", response_model=ReviewOut)
async def get_review(review_id: uuid.UUID, session: SessionDep) -> ReviewOut:
    review = await session.scalar(
        select(Review).where(Review.id == review_id).options(selectinload(Review.findings))
    )
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Review not found.")
    contract = await session.get(Document, review.contract_id)
    contract_title = contract.title if contract else "(deleted contract)"
    findings = [FindingOut.model_validate(f) for f in review.findings]

    report = None
    if review.status == ReviewStatus.COMPLETED and review.overall_risk:
        report = ReviewReport(
            contract_id=review.contract_id,
            contract_title=contract_title,
            provider=review.provider,
            model=review.model,
            summary=review.summary or "",
            overall_risk=review.overall_risk,  # type: ignore[arg-type]
            findings=findings,
            steps_used=review.steps_used,
            tokens_used=review.tokens_used,
            message=review.message,
            prompt_version=review.prompt_version,
        )

    return ReviewOut(
        id=review.id,
        contract_id=review.contract_id,
        contract_title=contract_title,
        provider=review.provider,
        status=ReviewStatus(review.status),
        steps=[ReviewStep.model_validate(s) for s in review.steps],
        findings=findings,
        steps_used=review.steps_used,
        tokens_used=review.tokens_used,
        message=review.message,
        created_at=review.created_at,
        completed_at=review.completed_at,
        report=report,
    )
