import uuid

from pydantic import BaseModel, Field

from app.llm.registry import ProviderName


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    provider: ProviderName | None = Field(
        default=None, description="LLM provider; defaults to DEFAULT_LLM_PROVIDER"
    )
    conversation_id: str | None = Field(default=None, max_length=100)
    document_ids: list[uuid.UUID] | None = Field(
        default=None, description="Restrict retrieval to these documents"
    )
    persist: bool = Field(
        default=True, description="Save the turn to conversation history (eval runs send false)"
    )


class SourceOut(BaseModel):
    """A chunk that was retrieved and shown to the model as numbered source `number`."""

    number: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int
    score: float


class Citation(BaseModel):
    source: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int
    snippet: str


class ChatUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: list[Citation]
    sources: list[SourceOut]
    usage: ChatUsage
    prompt_version: str
