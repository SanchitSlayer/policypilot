"""Embedding providers. All embedding calls in the app go through `EmbeddingProvider`."""

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider is misconfigured or its API call fails."""


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector of length `dim` per input text, in order."""
        ...


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(
                model=self.model, input=texts, dimensions=self.dim
            )
        except Exception as exc:
            raise EmbeddingError(f"OpenAI embedding request failed: {exc}") from exc
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        if any(len(v) != self.dim for v in vectors):
            raise EmbeddingError(
                f"Model {self.model} returned vectors that are not {self.dim}-dimensional; "
                "check EMBEDDING_MODEL and EMBEDDING_DIM."
            )
        return vectors


_WORD_RE = re.compile(r"[a-z0-9]+")


class FakeEmbeddingProvider:
    """Deterministic, offline embeddings: L2-normalised hashed bag of words.

    Texts that share words get a higher cosine similarity, so retrieval tests behave
    sensibly without any network calls.
    """

    name = "fake"
    model = "fake-hashed-bow"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def _bucket(self, word: str) -> int:
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dim

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in _WORD_RE.findall(text.lower()):
            vector[self._bucket(word)] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            vector[0] = 1.0  # avoid a zero vector, which has undefined cosine distance
            return vector
        return [x / norm for x in vector]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "fake":
        return FakeEmbeddingProvider(dim=settings.embedding_dim)
    if provider == "openai":
        if not settings.openai_api_key:
            raise EmbeddingError(
                "EMBEDDING_PROVIDER is 'openai' but OPENAI_API_KEY is not set. "
                "Set the key, or use EMBEDDING_PROVIDER=fake for offline development."
            )
        if not settings.embedding_model:
            raise EmbeddingError("EMBEDDING_MODEL must be set for the openai embedding provider.")
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )
    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER '{settings.embedding_provider}'.")


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """FastAPI dependency / app-wide accessor for the configured embedding provider."""
    return build_embedding_provider(get_settings())
