"""Conversation history: MongoDB in the app, an in-memory twin for unit tests."""

from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any, Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.llm.base import ChatMessage
from app.schemas.chat import Citation
from app.schemas.conversation import ConversationDetail, ConversationSummary, StoredMessage


def make_title(question: str, max_chars: int = 80) -> str:
    text = " ".join(question.split())
    return text if len(text) <= max_chars else text[:max_chars].rsplit(" ", 1)[0] + "…"


def build_turn(
    question: str, answer: str, citations: list[Citation], provider: str
) -> list[StoredMessage]:
    now = datetime.now(UTC)
    return [
        StoredMessage(role="user", content=question, created_at=now),
        StoredMessage(
            role="assistant", content=answer, citations=citations, provider=provider, created_at=now
        ),
    ]


class ConversationStore(Protocol):
    async def get_history(self, conversation_id: str) -> list[ChatMessage]:
        """Messages for the prompt (role + content only)."""
        ...

    async def append_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        citations: list[Citation],
        provider: str,
    ) -> None: ...

    async def list(self, limit: int = 50) -> list[ConversationSummary]: ...

    async def get(self, conversation_id: str) -> ConversationDetail | None: ...

    async def delete(self, conversation_id: str) -> bool: ...


class MongoConversationStore:
    def __init__(self, db: AsyncIOMotorDatabase, title_chars: int = 80) -> None:
        self._collection = db["conversations"]
        self._title_chars = title_chars

    async def get_history(self, conversation_id: str) -> list[ChatMessage]:
        doc = await self._collection.find_one(
            {"conversation_id": conversation_id}, {"messages.role": 1, "messages.content": 1}
        )
        if doc is None:
            return []
        return [ChatMessage(role=m["role"], content=m["content"]) for m in doc["messages"]]

    async def append_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        citations: list[Citation],
        provider: str,
    ) -> None:
        turn = build_turn(question, answer, citations, provider)
        now = turn[0].created_at
        await self._collection.update_one(
            {"conversation_id": conversation_id},
            {
                "$push": {
                    "messages": {
                        "$each": [m.model_dump(mode="json") | {"created_at": now} for m in turn]
                    }
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "title": make_title(question, self._title_chars),
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def list(self, limit: int = 50) -> list[ConversationSummary]:
        cursor = (
            self._collection.find(
                {},
                {
                    "_id": 0,
                    "conversation_id": 1,
                    "title": 1,
                    "created_at": 1,
                    "updated_at": 1,
                    "message_count": {"$size": "$messages"},
                },
            )
            .sort("updated_at", DESCENDING)
            .limit(limit)
        )
        return [ConversationSummary.model_validate(doc) async for doc in cursor]

    async def get(self, conversation_id: str) -> ConversationDetail | None:
        doc = await self._collection.find_one({"conversation_id": conversation_id}, {"_id": 0})
        if doc is None:
            return None
        return ConversationDetail.model_validate({**doc, "message_count": len(doc["messages"])})

    async def delete(self, conversation_id: str) -> bool:
        result = await self._collection.delete_one({"conversation_id": conversation_id})
        return result.deleted_count == 1


class InMemoryConversationStore:
    """Process-local store with the same behaviour; keeps the most recent conversations."""

    def __init__(self, max_conversations: int = 500) -> None:
        self._data: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max = max_conversations

    async def get_history(self, conversation_id: str) -> list[ChatMessage]:
        doc = self._data.get(conversation_id)
        messages = doc["messages"] if doc else []
        return [ChatMessage(role=m.role, content=m.content) for m in messages]

    async def append_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        citations: list[Citation],
        provider: str,
    ) -> None:
        turn = build_turn(question, answer, citations, provider)
        doc = self._data.setdefault(
            conversation_id,
            {"title": make_title(question), "created_at": turn[0].created_at, "messages": []},
        )
        doc["messages"].extend(turn)
        doc["updated_at"] = turn[0].created_at
        self._data.move_to_end(conversation_id)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def _detail(self, conversation_id: str, doc: dict[str, Any]) -> ConversationDetail:
        return ConversationDetail(
            conversation_id=conversation_id,
            title=doc["title"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            message_count=len(doc["messages"]),
            messages=doc["messages"],
        )

    async def list(self, limit: int = 50) -> list[ConversationSummary]:
        recent = list(reversed(self._data.items()))[:limit]
        return [
            ConversationSummary(**self._detail(cid, doc).model_dump(exclude={"messages"}))
            for cid, doc in recent
        ]

    async def get(self, conversation_id: str) -> ConversationDetail | None:
        doc = self._data.get(conversation_id)
        return self._detail(conversation_id, doc) if doc else None

    async def delete(self, conversation_id: str) -> bool:
        return self._data.pop(conversation_id, None) is not None
