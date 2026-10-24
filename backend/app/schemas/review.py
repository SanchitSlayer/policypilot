import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.registry import ProviderName
from app.models import FindingStatus, ReviewStatus


class ReviewRequest(BaseModel):
    document_id: uuid.UUID = Field(
        description="ID of an uploaded document with doc_type 'contract'"
    )
    provider: ProviderName | None = None


class ReviewCreated(BaseModel):
    review_id: uuid.UUID
    status: ReviewStatus


class PolicyCitation(BaseModel):
    source_id: str
    document_id: uuid.UUID
    document_title: str
    page_number: int
    snippet: str


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clause_id: str
    clause_title: str
    clause_page: int | None
    status: FindingStatus
    reason: str
    policy_citations: list[PolicyCitation]


class ReviewStep(BaseModel):
    index: int
    tool: str
    description: str
    ok: bool
    at: datetime


class ReviewReport(BaseModel):
    contract_id: uuid.UUID
    contract_title: str
    provider: str
    model: str | None
    summary: str
    overall_risk: Literal["low", "medium", "high"]
    findings: list[FindingOut]
    steps_used: int
    tokens_used: int
    message: str | None = Field(description="Set when a limit stopped the agent early")
    prompt_version: str | None


class ReviewOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    contract_title: str
    provider: str
    status: ReviewStatus
    steps: list[ReviewStep]
    findings: list[FindingOut] = Field(description="Findings recorded so far (live while running)")
    steps_used: int
    tokens_used: int
    message: str | None
    created_at: datetime
    completed_at: datetime | None
    report: ReviewReport | None = Field(description="Present once status is 'completed'")
