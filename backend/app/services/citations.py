"""Turn inline [n] markers in an answer into structured citations."""

import re
from collections.abc import Sequence

from app.schemas.chat import Citation
from app.services.retrieval import RetrievedChunk

# Matches [1], [2,3] and [2, 3]
CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def cited_numbers(answer: str) -> list[int]:
    """All numbers cited in the answer, in order of first appearance, without duplicates."""
    seen: dict[int, None] = {}
    for match in CITATION_RE.finditer(answer):
        for number in match.group(1).split(","):
            seen.setdefault(int(number), None)
    return list(seen)


def strip_invalid_citations(answer: str, num_sources: int) -> str:
    """Remove citation numbers that do not refer to an existing source."""

    def replace(match: re.Match[str]) -> str:
        valid = [n.strip() for n in match.group(1).split(",") if 1 <= int(n) <= num_sources]
        return f"[{', '.join(valid)}]" if valid else ""

    cleaned = CITATION_RE.sub(replace, answer)
    return re.sub(r" +([.,;:])", r"\1", cleaned)


def make_snippet(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def build_citations(
    answer: str, sources: Sequence[RetrievedChunk], snippet_chars: int
) -> list[Citation]:
    citations: list[Citation] = []
    for number in cited_numbers(answer):
        if not 1 <= number <= len(sources):
            continue  # hallucinated source number
        source = sources[number - 1]
        citations.append(
            Citation(
                source=number,
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                document_title=source.document_title,
                page_number=source.page_number,
                snippet=make_snippet(source.content, snippet_chars),
            )
        )
    return citations
