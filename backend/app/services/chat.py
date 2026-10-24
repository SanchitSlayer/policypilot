"""RAG chat: retrieve sources, prompt the selected provider, return a cited answer."""

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.base import ChatMessage, LLMError, LLMProvider, LLMResponse
from app.llm.embeddings import EmbeddingProvider
from app.llm.prompts import (
    NO_ANSWER_TEXT,
    PROMPT_VERSION,
    RAG_SYSTEM_PROMPT,
    build_rag_user_message,
)
from app.llm.usage import UsageLogger, with_usage_logging
from app.schemas.chat import ChatRequest, ChatResponse, ChatUsage, SourceOut
from app.services.citations import build_citations, strip_invalid_citations
from app.services.conversations import ConversationStore
from app.services.retrieval import RetrievedChunk, retrieve

# Short follow-ups ("what about companies?") are retrieved together with the previous question.
# Kept low: a full question of 6+ words should be searched on its own.
FOLLOW_UP_MAX_WORDS = 5


@dataclass
class PreparedChat:
    conversation_id: str
    question: str
    provider: LLMProvider
    sources: list[RetrievedChunk]
    messages: list[ChatMessage]


def sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        embedder: EmbeddingProvider,
        store: ConversationStore,
        settings: Settings,
        provider_factory: Callable[[str], LLMProvider],
        usage_logger: UsageLogger,
    ) -> None:
        self._provider_factory = provider_factory
        self._usage_logger = usage_logger
        self._session = session
        self._embedder = embedder
        self._store = store
        self._settings = settings

    async def prepare(self, request: ChatRequest) -> PreparedChat:
        """Resolve the provider, load history and retrieve sources. Raises
        ProviderNotConfiguredError before doing any work if the provider is unusable."""
        provider = with_usage_logging(
            self._provider_factory(request.provider or self._settings.default_llm_provider),
            feature="chat",
            usage_logger=self._usage_logger,
            prompt_version=PROMPT_VERSION,
        )
        conversation_id = request.conversation_id or uuid.uuid4().hex
        history = await self._store.get_history(conversation_id)
        history = history[-2 * self._settings.chat_history_turns :]

        sources = await retrieve(
            self._session,
            self._embedder,
            self._retrieval_query(request.question, history),
            top_k=self._settings.retrieval_top_k,
            min_score=self._settings.retrieval_min_score,
            document_ids=request.document_ids,
        )
        messages = [
            *history,
            ChatMessage(role="user", content=build_rag_user_message(request.question, sources)),
        ]
        return PreparedChat(conversation_id, request.question, provider, sources, messages)

    @staticmethod
    def _retrieval_query(question: str, history: list[ChatMessage]) -> str:
        previous = next((m.content for m in reversed(history) if m.role == "user"), None)
        if previous and len(question.split()) <= FOLLOW_UP_MAX_WORDS:
            return f"{previous}\n{question}"
        return question

    async def answer(self, request: ChatRequest) -> ChatResponse:
        prepared = await self.prepare(request)
        if not prepared.sources:
            response = self._no_sources_response(prepared)
        else:
            response = await prepared.provider.chat(
                prepared.messages,
                system=RAG_SYSTEM_PROMPT,
                temperature=self._settings.chat_temperature,
            )
        return await self._finish(prepared, response)

    async def stream(self, prepared: PreparedChat) -> AsyncIterator[str]:
        """Server-Sent Events: `token`* then `citations` then `done` (or `error`)."""
        if not prepared.sources:
            response = self._no_sources_response(prepared)
            yield sse("token", {"text": response.text})
        else:
            stream = prepared.provider.stream_chat(
                prepared.messages,
                system=RAG_SYSTEM_PROMPT,
                temperature=self._settings.chat_temperature,
            )
            try:
                async for delta in stream:
                    yield sse("token", {"text": delta})
            except LLMError as exc:
                yield sse("error", {"detail": str(exc)})
                return
            assert stream.response is not None
            response = stream.response

        result = await self._finish(prepared, response)
        yield sse(
            "citations",
            {
                "conversation_id": result.conversation_id,
                "citations": [c.model_dump(mode="json") for c in result.citations],
                "sources": [s.model_dump(mode="json") for s in result.sources],
            },
        )
        yield sse(
            "done",
            {
                "conversation_id": result.conversation_id,
                "answer": result.answer,
                "usage": result.usage.model_dump(),
                "prompt_version": result.prompt_version,
            },
        )

    def _no_sources_response(self, prepared: PreparedChat) -> LLMResponse:
        """Nothing relevant was retrieved: answer honestly without calling the model."""
        return LLMResponse(
            text=NO_ANSWER_TEXT,
            model=prepared.provider.model,
            provider=prepared.provider.name,
            stop_reason="no_sources",
        )

    async def _finish(self, prepared: PreparedChat, response: LLMResponse) -> ChatResponse:
        answer = strip_invalid_citations(response.text, len(prepared.sources)).strip()
        citations = build_citations(answer, prepared.sources, self._settings.citation_snippet_chars)
        await self._store.append_turn(
            prepared.conversation_id,
            question=prepared.question,
            answer=answer,
            citations=citations,
            provider=response.provider,
        )
        return ChatResponse(
            conversation_id=prepared.conversation_id,
            answer=answer,
            citations=citations,
            sources=[
                SourceOut(
                    number=number,
                    chunk_id=s.chunk_id,
                    document_id=s.document_id,
                    document_title=s.document_title,
                    page_number=s.page_number,
                    score=s.score,
                )
                for number, s in enumerate(prepared.sources, start=1)
            ],
            usage=ChatUsage(
                provider=response.provider,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
            ),
            prompt_version=PROMPT_VERSION,
        )
