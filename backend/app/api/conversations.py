from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.chat import get_conversation_store
from app.schemas.conversation import ConversationDetail, ConversationSummary
from app.services.conversations import ConversationStore

router = APIRouter(prefix="/conversations", tags=["conversations"])

StoreDep = Annotated[ConversationStore, Depends(get_conversation_store)]


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    store: StoreDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[ConversationSummary]:
    """Most recently updated first."""
    return await store.list(limit)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, store: StoreDep) -> ConversationDetail:
    conversation = await store.get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, store: StoreDep) -> Response:
    if not await store.delete(conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
