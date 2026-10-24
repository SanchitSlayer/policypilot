import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReviewStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingStatus(StrEnum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    NEEDS_REVIEW = "needs_review"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=ReviewStatus.RUNNING)
    summary: Mapped[str | None] = mapped_column(Text)
    overall_risk: Mapped[str | None] = mapped_column(String(10))
    # Live progress log: [{index, tool, description, ok, at}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    steps_used: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    # Why a review ended early (step limit, timeout) or failed
    message: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Finding.position",
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("review_id", "clause_id", name="uq_findings_review_clause"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)  # clause order in the contract
    clause_id: Mapped[str] = mapped_column(String(20))
    clause_title: Mapped[str] = mapped_column(String(300))
    clause_page: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    # [{source_id, document_id, document_title, page_number, snippet}]
    policy_citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    review: Mapped[Review] = relationship(back_populates="findings")
