from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import EmbedderDep, SessionDep, SettingsDep
from app.llm.base import LLMError, LLMProvider, ProviderNotConfiguredError
from app.llm.registry import get_provider
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService, PreparedChat
from app.services.conversations import ConversationStore, get_conversation_store

router = APIRouter(prefix="/chat", tags=["chat"])


def get_provider_factory() -> Callable[[str], LLMProvider]:
    return get_provider


def get_chat_service(
    session: SessionDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    store: Annotated[ConversationStore, Depends(get_conversation_store)],
    provider_factory: Annotated[Callable[[str], LLMProvider], Depends(get_provider_factory)],
) -> ChatService:
    return ChatService(session, embedder, store, settings, provider_factory)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, service: ChatServiceDep) -> ChatResponse:
    """Answer a question with citations (non-streaming; used by tests and the eval script)."""
    try:
        return await service.answer(request)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat_stream(request: ChatRequest, service: ChatServiceDep) -> StreamingResponse:
    """Stream the answer as Server-Sent Events.

    Events: `token` {text} (repeated), then `citations` {conversation_id, citations, sources},
    then `done` {conversation_id, answer, usage, prompt_version}. On a provider failure
    mid-stream an `error` {detail} event is sent instead.
    """
    try:
        # Retrieval happens before streaming so setup errors get a proper HTTP status.
        prepared: PreparedChat = await service.prepare(request)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StreamingResponse(
        service.stream(prepared),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
