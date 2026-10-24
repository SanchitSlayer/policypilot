import uuid

from app.services.citations import (
    build_citations,
    cited_numbers,
    make_snippet,
    strip_invalid_citations,
)
from app.services.retrieval import RetrievedChunk


def _source(title: str, page: int, content: str = "Some policy text.") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        page_number=page,
        content=content,
        score=0.8,
    )


def test_cited_numbers_in_first_appearance_order_without_duplicates() -> None:
    answer = "Passport is valid [2]. So is Aadhaar [1, 3]. Passport again [2][1]."
    assert cited_numbers(answer) == [2, 1, 3]


def test_strip_invalid_citations_removes_nonexistent_sources() -> None:
    answer = "Valid [1]. Hallucinated [7]. Mixed [2, 9]. End."
    assert (
        strip_invalid_citations(answer, num_sources=2) == "Valid [1]. Hallucinated. Mixed [2]. End."
    )


def test_build_citations_maps_numbers_to_sources_and_skips_invalid() -> None:
    sources = [_source("KYC Direction", 12), _source("Digital Lending", 4)]

    citations = build_citations("A [2]. B [1]. C [5]. D [0].", sources, snippet_chars=100)

    assert [(c.source, c.document_title, c.page_number) for c in citations] == [
        (2, "Digital Lending", 4),
        (1, "KYC Direction", 12),
    ]
    assert citations[0].document_id == sources[1].document_id


def test_no_citations_when_answer_has_no_markers() -> None:
    assert build_citations("No markers here.", [_source("A", 1)], snippet_chars=50) == []


def test_snippet_is_truncated_on_a_word_boundary() -> None:
    text = "Officially valid documents include the passport and the driving licence."
    snippet = make_snippet(text, max_chars=30)
    assert snippet == "Officially valid documents…"
    assert make_snippet("short  text\n here", 50) == "short text here"
