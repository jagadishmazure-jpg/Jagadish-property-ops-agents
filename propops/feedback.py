"""Feedback capture with PII scrubbing before storage.

Free-text feedback is scrubbed (see pii.py) before it is written to the
JSONL store. Session/turn linkage is required; FeedbackError is raised
for invalid payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from .pii import scrub


class FeedbackError(Exception):
    pass


@dataclass
class Feedback:
    session_id: str
    turn: int
    kind: str            # thumbs_up | thumbs_down | correction
    text: str            # scrubbed
    redactions: int
    wo_id: str = ""


class FeedbackStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, session_id: str, turn: int, kind: str,
            text: str, wo_id: str = "") -> Feedback:
        if kind not in {"thumbs_up", "thumbs_down", "correction"}:
            raise FeedbackError(f"unknown feedback kind: {kind}")
        if not session_id or turn < 0:
            raise FeedbackError("session_id and non-negative turn required")
        clean, n = scrub(text)
        fb = Feedback(session_id, turn, kind, clean, n, wo_id)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(fb)) + "\n")
        return fb

    def all(self) -> list[Feedback]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                out.append(Feedback(**json.loads(line)))
        return out
