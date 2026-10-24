"""Minimal text-only PDF writer (Helvetica, no dependencies) for tests and demo data."""

import textwrap


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


CHARS_PER_LINE = 95
LINES_PER_PAGE = 56


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=CHARS_PER_LINE) or [""])
    return lines


def _content_stream(text: str) -> bytes:
    lines = _wrap(text)
    ops = ["BT", "/F1 10 Tf", "12 TL", "50 750 Td"]
    ops += [f"({_escape(line)}) Tj T*" for line in lines if text]
    ops.append("ET")
    return "\n".join(ops).encode("latin-1", errors="replace")


def make_pdf(pages: list[str]) -> bytes:
    """Build a valid PDF with one page per string (an empty string gives a blank page)."""
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] "
            f"/Count {len(pages)} >>"
        ).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, text in zip(page_ids, pages, strict=True):
        stream = _content_stream(text)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>"
        ).encode()
        objects[page_id + 1] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for object_id in sorted(objects):
        offsets[object_id] = len(out)
        out += f"{object_id} 0 obj\n".encode() + objects[object_id] + b"\nendobj\n"

    xref_offset = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for object_id in range(1, size):
        out += f"{offsets[object_id]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return bytes(out)


def make_text_pdf(text: str) -> bytes:
    """Lay out long text over as many pages as needed."""
    lines = _wrap(text)
    pages = [
        "\n".join(lines[start : start + LINES_PER_PAGE])
        for start in range(0, len(lines), LINES_PER_PAGE)
    ]
    return make_pdf(pages or [""])
