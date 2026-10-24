"""PDF text extraction that keeps page numbers."""

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"


class PdfExtractionError(ValueError):
    """Raised when a file cannot be parsed as a PDF."""


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based, as printed in a PDF viewer
    text: str


_INLINE_SPACE_RE = re.compile(r"[ \t\f\v ]+")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")


def clean_text(raw: str) -> str:
    """Collapse runs of spaces within lines and limit blank lines, keeping paragraph breaks."""
    text = raw.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [_INLINE_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_NEWLINES_RE.sub("\n\n", "\n".join(lines)).strip()


def is_pdf(data: bytes) -> bool:
    return data.lstrip()[:5] == PDF_MAGIC


def extract_pages(data: bytes) -> tuple[int, list[PageText]]:
    """Return (total page count, non-empty pages with cleaned text)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PdfExtractionError("Encrypted PDFs are not supported.")
        pages: list[PageText] = []
        for index, page in enumerate(reader.pages, start=1):
            text = clean_text(page.extract_text() or "")
            if text:
                pages.append(PageText(page_number=index, text=text))
        return len(reader.pages), pages
    except PdfReadError as exc:
        raise PdfExtractionError(f"Could not read PDF: {exc}") from exc
