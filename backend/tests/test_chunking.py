import pytest

from app.services.chunking import chunk_pages, get_encoding
from app.services.pdf import PageText, clean_text

ENC = get_encoding("cl100k_base")


def _text_with_tokens(n: int, word: str = "policy") -> str:
    """A string that encodes to exactly n tokens (' policy' is a single token)."""
    text = (" " + word) * n
    assert len(ENC.encode(text)) == n
    return text


def test_windows_overlap_by_the_configured_number_of_tokens() -> None:
    page_text = " ".join(f"clause{i}" for i in range(600))
    tokens = ENC.encode(page_text)

    chunks = chunk_pages([PageText(1, page_text)], chunk_size=500, overlap=80)

    step = 500 - 80
    expected_starts = list(range(0, len(tokens), step))
    expected_starts = [s for s in expected_starts if s == 0 or s - step + 500 < len(tokens)]
    assert [c.content for c in chunks] == [
        ENC.decode(tokens[s : s + 500]).strip() for s in expected_starts
    ]
    overlap_text = ENC.decode(tokens[step:500]).strip()
    assert chunks[0].content.endswith(overlap_text)
    assert chunks[1].content.startswith(overlap_text)
    assert all(c.token_count <= 500 for c in chunks)
    assert chunks[-1].token_count == len(tokens) - expected_starts[-1]


def test_short_page_gives_single_chunk() -> None:
    chunks = chunk_pages([PageText(3, _text_with_tokens(40))], chunk_size=500, overlap=80)

    assert len(chunks) == 1
    assert chunks[0].page_number == 3
    assert chunks[0].token_count == 40


def test_chunks_never_cross_page_boundaries() -> None:
    pages = [
        PageText(1, _text_with_tokens(130, "alpha")),
        PageText(2, _text_with_tokens(30, "beta")),
        PageText(4, _text_with_tokens(70, "gamma")),
    ]

    chunks = chunk_pages(pages, chunk_size=50, overlap=10)

    for chunk in chunks:
        words = set(chunk.content.split())
        assert len(words) == 1, f"chunk {chunk.chunk_index} mixes pages: {words}"
        expected_page = {"alpha": 1, "beta": 2, "gamma": 4}[words.pop()]
        assert chunk.page_number == expected_page
    assert [c.page_number for c in chunks] == [1, 1, 1, 2, 4, 4]
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_window_settings_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_pages([PageText(1, "text")], chunk_size=size, overlap=overlap)


def test_clean_text_collapses_spaces_but_keeps_paragraphs() -> None:
    raw = "1.  Customer   Due\tDiligence\r\n\r\n\r\n\r\n2. Records\x00 kept  "
    assert clean_text(raw) == "1. Customer Due Diligence\n\n2. Records kept"
