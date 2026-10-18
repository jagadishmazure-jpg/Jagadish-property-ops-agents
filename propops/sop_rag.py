"""TF-IDF SOP retrieval with `file §section` citations and explicit not-found.

Title-only intro chunks are skipped (they caused false positives in a
sibling repo: a bare title matched on a single shared word).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

_DOCS = {
    "sop-01-triage-playbook.md": "Triage playbook",
    "sop-02-dispatch.md": "Technician dispatch",
    "sop-03-preventive-maintenance.md": "Preventive maintenance",
    "sop-04-tenant-communication.md": "Tenant communication",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class Chunk:
    doc: str
    section: str
    text: str


def load_chunks(docs_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for fname in _DOCS:
        path = docs_dir / fname
        if not path.exists():
            continue
        section = _DOCS[fname]
        for para in path.read_text().split("\n\n"):
            # strip markdown heading lines; skip chunks that are only a title
            body = "\n".join(
                ln for ln in para.splitlines()
                if not ln.lstrip().startswith("#")).strip()
            if not body:
                continue            # skip title-only intro chunks
            chunks.append(Chunk(fname, section, body))
    return chunks


@dataclass
class Hit:
    doc: str
    section: str
    score: float
    excerpt: str


def search(chunks: list[Chunk], query: str, top_k: int = 3) -> list[Hit]:
    q = _tokens(query)
    if not q:
        return []
    df: dict[str, int] = {}
    tok_chunks = [_tokens(c.text) for c in chunks]
    for toks in tok_chunks:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    scored = []
    for chunk, toks in zip(chunks, tok_chunks):
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in q:
            if t in tf:
                score += tf[t] * math.log((n + 1) / (df[t] + 1))
        if score > 0:
            words = chunk.text.split()
            scored.append(Hit(chunk.doc, chunk.section, round(score, 3),
                              " ".join(words[:40])))
    scored.sort(key=lambda h: -h.score)
    return scored[:top_k]
