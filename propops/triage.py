"""Work-order triage engine — the repo's first differentiator.

Priority = 0.5*urgency + 0.3*tenant-impact + 0.2*asset-criticality, on a
0..5 scale, mapped to P1..P4. Every decision cites the exact rule that
fired. Repeat issues (3+ same category + unit in 30 days) bump one level
(TR-ESC-01).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

SAFETY_CATEGORIES = {"safety"}
CRITICAL_ASSETS = {"boiler", "elevator", "water-main", "fire-alarm"}


@dataclass
class TriageDecision:
    wo_id: str
    priority: str
    score: float
    breakdown: str
    rules: list[str]


def _impact_band(residents: int) -> float:
    if residents >= 20:
        return 5.0
    if residents >= 5:
        return 4.0
    if residents >= 2:
        return 3.0
    return 2.0


def _criticality(category: str, asset: str | None) -> float:
    if category in SAFETY_CATEGORIES:
        return 5.0
    if asset in CRITICAL_ASSETS:
        return 4.0
    if category in {"plumbing", "electrical", "hvac"}:
        return 3.0
    return 2.0


def _is_repeat(conn: sqlite3.Connection, wo_id: str) -> bool:
    row = conn.execute(
        "SELECT unit_id, category, reported_at FROM work_orders "
        "WHERE wo_id = ?", (wo_id,)).fetchone()
    if not row:
        return False
    unit, cat, reported = row
    count = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE unit_id = ? AND category = ? "
        "AND julianday(?) - julianday(reported_at) <= 30",
        (unit, cat, reported)).fetchone()[0]
    return count >= 3


def triage(conn: sqlite3.Connection, wo_id: str) -> TriageDecision:
    row = conn.execute(
        "SELECT urgency, residents_affected, category, asset "
        "FROM work_orders WHERE wo_id = ?", (wo_id,)).fetchone()
    if not row:
        raise ValueError(f"unknown work order {wo_id}")
    urgency, residents, category, asset = row

    impact = _impact_band(residents)
    crit = _criticality(category, asset)
    score = round(0.5 * urgency + 0.3 * impact + 0.2 * crit, 2)

    rules: list[str] = []
    if category in SAFETY_CATEGORIES:
        priority, rule = "P1", "TR-P1-02 (safety category auto-P1)"
    elif urgency >= 5 or (urgency >= 4 and residents >= 20):
        priority, rule = "P1", "TR-P1-01 (urgency>=5 or urgency>=4 with 20+ residents)"
    elif urgency >= 4 or asset in CRITICAL_ASSETS:
        priority, rule = "P2", "TR-P2-01 (urgency>=4 or critical asset)"
    elif urgency >= 3:
        priority, rule = "P3", "TR-P3-01 (urgency 3)"
    else:
        priority, rule = "P4", "TR-P4-01 (urgency<=2)"
    rules.append(rule)

    if _is_repeat(conn, wo_id) and priority != "P1":
        priority = {"P2": "P1", "P3": "P2", "P4": "P3"}[priority]
        rules.append("TR-ESC-01 (repeat issue: 3+ same category+unit in 30d, bumped one level)")

    breakdown = (f"0.5*{urgency}(urgency) + 0.3*{impact}(tenant-impact) "
                 f"+ 0.2*{crit}(asset-criticality) = {score}")
    conn.execute("UPDATE work_orders SET priority = ? WHERE wo_id = ?",
                 (priority, wo_id))
    conn.commit()
    return TriageDecision(wo_id, priority, score, breakdown, rules)
