"""Split a contract into clauses: numbered headings first, paragraph blocks as a fallback."""

import re
from dataclasses import dataclass

from app.services.pdf import PageText

# "1. Definitions", "12) Term", "Clause 3", "Section 4.2:", "Article 5 -"
_TOP_LEVEL_RE = re.compile(
    r"^(?:(?:clause|section|article)\s+(?P<word_num>\d{1,3})(?:\.\d+)*\b[.:)\-–]?|"
    r"(?P<num>\d{1,2})[.)])\s+(?P<rest>\S.*)?$",
    re.IGNORECASE,
)
# "2.1 Data retention" (used only when there are no top-level headings)
_SUB_LEVEL_RE = re.compile(r"^(?P<num>\d{1,2}\.\d{1,2})\.?\s+(?P<rest>[A-Z].*)$")

MIN_HEADINGS = 2
FALLBACK_MIN_WORDS = 60
MAX_TITLE_CHARS = 80


@dataclass(frozen=True)
class Clause:
    id: str
    title: str
    text: str
    page: int


@dataclass(frozen=True)
class _Line:
    page: int
    text: str


def _lines(pages: list[PageText]) -> list[_Line]:
    """All lines in order; a blank line marks each page break (a possible paragraph end)."""
    return [_Line(p.page_number, line.strip()) for p in pages for line in [*p.text.split("\n"), ""]]


def _title_from(heading: str) -> str:
    """'5. Data Retention. Vendor shall…' -> '5. Data Retention'."""
    title = re.split(r"(?<=[A-Za-z)])\.\s", heading, maxsplit=1)[0].rstrip(".:").strip()
    if len(title) > MAX_TITLE_CHARS:
        title = title[:MAX_TITLE_CHARS].rsplit(" ", 1)[0] + "…"
    return title


def _split_on(lines: list[_Line], pattern: re.Pattern[str]) -> list[Clause]:
    starts = [i for i, line in enumerate(lines) if pattern.match(line.text)]
    clauses: list[Clause] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = [line.text for line in lines[start:end]]
        text = "\n".join(block).strip()
        clauses.append(
            Clause(id=f"c{n + 1}", title=_title_from(block[0]), text=text, page=lines[start].page)
        )
    return clauses


def _split_paragraphs(lines: list[_Line]) -> list[Clause]:
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    page = lines[0].page if lines else 1
    for line in lines:
        if not line.text:
            if current and len(" ".join(current).split()) >= FALLBACK_MIN_WORDS:
                blocks.append((page, current))
                current = []
            continue
        if not current:
            page = line.page
        current.append(line.text)
    if current:
        blocks.append((page, current))

    clauses = []
    for n, (block_page, block) in enumerate(blocks, start=1):
        text = " ".join(block)
        words = text.split()
        title = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
        clauses.append(Clause(id=f"c{n}", title=title, text=text, page=block_page))
    return clauses


def split_clauses(pages: list[PageText], max_clauses: int = 30) -> list[Clause]:
    lines = _lines(pages)
    for pattern in (_TOP_LEVEL_RE, _SUB_LEVEL_RE):
        clauses = _split_on(lines, pattern)
        if len(clauses) >= MIN_HEADINGS:
            return clauses[:max_clauses]
    return _split_paragraphs(lines)[:max_clauses]
