"""T1–T4 escalation tiers + confirmation gates.

  T1 routine      — dispatcher handles alone
  T2 supervisor   — P1 work orders, repeat issues
  T3 manager      — emergency dispatch, lease-violation enforcement
  T4 director     — building-wide shutdowns, mass tenant relocation

Emergency dispatch and lease-violation enforcement always require a
human confirmation gate; the gate denies on timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Tier:
    name: str
    owner: str
    sla_minutes: int


TIERS = {
    "T1": Tier("T1", "dispatcher", 240),
    "T2": Tier("T2", "supervisor", 60),
    "T3": Tier("T3", "property manager", 30),
    "T4": Tier("T4", "director", 15),
}

# actions that always need a human confirmation before executing
GATED_ACTIONS = {"emergency_dispatch", "lease_violation_enforcement",
                 "building_shutdown"}


class GateDenied(Exception):
    pass


class ConfirmationGate:
    def __init__(self, approver: Callable[[str], bool] | None = None) -> None:
        self._approver = approver or (lambda action: False)

    def check(self, action: str) -> None:
        if action in GATED_ACTIONS and not self._approver(action):
            raise GateDenied(
                f"human confirmation required and not granted for {action}")


def tier_for(priority: str, repeat: bool = False) -> str:
    if priority == "P1":
        return "T2"
    if repeat:
        return "T2"
    if priority == "P2":
        return "T1"
    return "T1"
