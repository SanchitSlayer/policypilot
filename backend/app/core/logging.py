"""Logging setup with a redaction filter, so personal data does not end up in log storage.

The app never logs prompts, answers or document text on purpose; the filter is defence in depth
for messages that could carry them indirectly (exception text, third-party libraries).
"""

import logging
import re

_REDACTIONS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[pan]"),  # Indian PAN
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[aadhaar]"),  # 12-digit Aadhaar-like
    (re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{9}(?!\d)"), "[phone]"),  # Indian mobile
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    redacting = RedactingFilter()
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(redacting)
