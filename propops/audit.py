"""Hash-chained audit log.

Every action appends an entry whose hash covers the previous hash, so any
tampering breaks verify_chain(). Entries never echo raw row data.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field


@dataclass
class AuditEntry:
    seq: int
    ts: float
    actor: str
    action: str
    details: str
    prev_hash: str
    hash: str = field(default="")


def _hash(entry: AuditEntry) -> str:
    payload = json.dumps([entry.seq, entry.ts, entry.actor, entry.action,
                          entry.details, entry.prev_hash], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class AuditLog:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def record(self, actor: str, action: str, details: str = "") -> AuditEntry:
        prev = self.entries[-1].hash if self.entries else "GENESIS"
        entry = AuditEntry(len(self.entries), round(time.time(), 3),
                           actor, action, details[:500], prev)
        entry.hash = _hash(entry)
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        prev = "GENESIS"
        for i, e in enumerate(self.entries):
            if e.seq != i or e.prev_hash != prev or _hash(e) != e.hash:
                return False
            prev = e.hash
        return True
