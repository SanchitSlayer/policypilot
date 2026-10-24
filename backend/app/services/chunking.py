"""Token-based chunking that never lets a chunk span two pages."""

from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from app.services.pdf import PageText


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    page_number: int
    content: str
    token_count: int


@lru_cache
def get_encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def chunk_pages(
    pages: list[PageText],
    *,
    chunk_size: int,
    overlap: int,
    encoding_name: str = "cl100k_base",
) -> list[TextChunk]:
    """Split each page into windows of `chunk_size` tokens that overlap by `overlap` tokens.

    Windows restart at every page boundary, so each chunk has exactly one page number.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    encoding = get_encoding(encoding_name)
    step = chunk_size - overlap
    chunks: list[TextChunk] = []

    for page in pages:
        tokens = encoding.encode(page.text)
        start = 0
        while start < len(tokens):
            window = tokens[start : start + chunk_size]
            content = encoding.decode(window).strip()
            if content:
                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        page_number=page.page_number,
                        content=content,
                        token_count=len(window),
                    )
                )
            if start + chunk_size >= len(tokens):
                break
            start += step

    return chunks
