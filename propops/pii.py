"""PII scrubbing — always applied BEFORE feedback text is stored.

Email, phone, SSN, and payment-card patterns are replaced with
placeholders; the redaction count is kept for the audit trail.
"""

from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
     "[EMAIL]"),
    # Phone: (555) 123-4567, +1 (555) 123-4567, 555.123.4567, 555-123-4567.
    # Placed before the generic digit-run so the specific match wins.
    (re.compile(r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)\s?|\d{3}[-.\s]?)"
                r"\d{3}[-.\s]?\d{4}\b"),
     "[PHONE]"),
    # SSN: 123-45-6789. The \b anchors keep dates like 2026-10-18 intact.
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # Card: four groups of four (space or dash) or 13-16 contiguous digits.
    # The old loose pattern also ate date pairs and runs of unit numbers.
    (re.compile(r"\b(?:\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}|\d{13,16})\b"), "[CARD]"),
]


def scrub(text: str) -> tuple[str, int]:
    """Return (scrubbed_text, redaction_count)."""
    count = 0
    for pattern, placeholder in _PATTERNS:
        text, n = pattern.subn(placeholder, text)
        count += n
    return text, count
