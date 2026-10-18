"""Technician-dispatch optimizer — the repo's second differentiator.

Skill is a hard filter (no skill -> never assigned). Among qualified techs
on an active shift, rank by:

    0.40 * skill_depth + 0.35 * proximity + 0.25 * (1 - load)

Every assignment carries a per-factor breakdown. Raises
NoTechAvailable instead of guessing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

MAX_LOAD = 5  # active WOs at which a tech is considered fully loaded


class NoTechAvailable(Exception):
    pass


@dataclass
class Assignment:
    wo_id: str
    tech_id: str
    score: float
    breakdown: str


def _skill_depth(skills: str, category: str) -> float:
    have = [s.strip() for s in skills.split(",")]
    if category not in have:
        return 0.0
    # deeper bench = techs whose skill list is short (specialists)
    return round(1.0 / len(have) + 0.5, 2)


def dispatch(conn: sqlite3.Connection, wo_id: str) -> Assignment:
    wo = conn.execute(
        "SELECT category, unit_id FROM work_orders WHERE wo_id = ?",
        (wo_id,)).fetchone()
    if not wo:
        raise ValueError(f"unknown work order {wo_id}")
    category, unit_id = wo
    bldg = conn.execute("SELECT building_id FROM units WHERE unit_id = ?",
                        (unit_id,)).fetchone()[0]

    cands = []
    for tech_id, name, skills, home, shift, active in conn.execute(
            "SELECT tech_id, name, skills, home_building, shift, active_wos "
            "FROM technicians"):
        depth = _skill_depth(skills, category)
        if depth == 0.0:
            continue                      # skill hard filter
        if shift == "off":
            continue                      # off-shift techs excluded
        proximity = 1.0 if home == bldg else 0.5
        load = min(active / MAX_LOAD, 1.0)
        score = round(0.40 * depth + 0.35 * proximity + 0.25 * (1 - load), 4)
        breakdown = (f"0.40*{depth}(skill) + 0.35*{proximity}(proximity) + "
                     f"0.25*{round(1 - load, 2)}(availability) = {score}")
        cands.append((score, tech_id, breakdown))

    if not cands:
        raise NoTechAvailable(
            f"no qualified on-shift technician for {category} ({wo_id})")
    cands.sort(reverse=True)
    score, tech_id, breakdown = cands[0]
    conn.execute("UPDATE technicians SET active_wos = active_wos + 1 "
                 "WHERE tech_id = ?", (tech_id,))
    conn.execute("UPDATE work_orders SET status = 'assigned' WHERE wo_id = ?",
                 (wo_id,))
    conn.commit()
    return Assignment(wo_id, tech_id, score, breakdown)
