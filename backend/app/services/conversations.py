"""Conversation memory. In-memory for now; Phase 5 adds a MongoDB implementation."""

from collections import OrderedDict
from typing import Protocol

from app.llm.base import ChatMessage


class ConversationStore(Protocol):
    async def get_messages(self, conversation_id: str) -> list[ChatMessage]: ...

    async def append(self, conversation_id: str, messages: list[ChatMessage]) -> None: ...


class InMemoryConversationStore:
    """Process-local store; keeps the most recently used `max_conversations`."""

    def __init__(self, max_conversations: int = 500) -> None:
        self._data: OrderedDict[str, list[ChatMessage]] = OrderedDict()
        self._max = max_conversations

    async def get_messages(self, conversation_id: str) -> list[ChatMessage]:
        return list(self._data.get(conversation_id, []))

    async def append(self, conversation_id: str, messages: list[ChatMessage]) -> None:
        self._data.setdefault(conversation_id, []).extend(messages)
        self._data.move_to_end(conversation_id)
        while len(self._data) > self._max:
            self._data.popitem(last=False)


_store = InMemoryConversationStore()


def get_conversation_store() -> ConversationStore:
    return _store
