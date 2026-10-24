from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import Citation


class StoredMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    provider: str | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetail(ConversationSummary):
    messages: list[StoredMessage]
