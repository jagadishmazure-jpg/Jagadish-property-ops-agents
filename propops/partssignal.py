"""Parts-supplier lead-time feed.

FakePartsFeed is seeded and deterministic. LivePartsFeed is a stub that
raises SignalGap — the agent must surface the gap explicitly and must
never hallucinate lead times.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


class SignalGap(Exception):
    """Live signal unavailable; caller must say so explicitly."""


@dataclass
class LeadTime:
    part: str
    days: int
    source: str


_FAKE_LEADS = {
    "water-main coupling": 2,
    "boiler pressure valve": 6,
    "elevator door sensor": 4,
    "hvac compressor": 9,
    "dishwasher pump": 3,
}


class FakePartsFeed:
    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def lead_time(self, part: str) -> LeadTime:
        base = _FAKE_LEADS.get(part.lower(), 5)
        jitter = self._rng.randint(-1, 1)
        return LeadTime(part, max(1, base + jitter), "fake")


class LivePartsFeed:
    def lead_time(self, part: str) -> LeadTime:
        raise SignalGap(
            f"live parts feed not connected; cannot quote a lead time for {part!r}")
