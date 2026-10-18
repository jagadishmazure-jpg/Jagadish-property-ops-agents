"""Technician-dispatch optimizer — the repo's second differentiator.

Skill is a hard filter (no skill -> never assigned). Work-order categories
map to technician skills (DSP-SKILL-01: appliance -> appliances,
structural -> carpentry). Only open work orders are dispatched
(DSP-OPEN-01), and a technician at MAX_LOAD is never assigned
(DSP-LOAD-01, SOP-02). Safety work orders are not auto-dispatched: no
technician carries a safety skill, so the optimizer says so instead of
guessing. Among qualified techs on an active shift below max load, rank by:

    0.40 * skill_depth + 0.35 * proximity + 0.25 * (1 - load)

Every assignment carries a per-factor breakdown. Raises
NoTechAvailable instead of guessing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

MAX_LOAD = 5  # active WOs at which a tech is considered fully loaded


# Work-order category -> required technician skill, where the names differ.
CATEGORY_SKILL = {"appliance": "appliances", "structural": "carpentry"}


class NoTechAvailable(Exception):
    pass


class NotDispatchable(ValueError):
    """The work order is not open (already assigned, in progress or closed)."""


@dataclass
class Assignment:
    wo_id: str
    tech_id: str
    score: float
    breakdown: str


def _skill_depth(skills: str, category: str) -> float:
    have = [s.strip() for s in skills.split(",")]
    if CATEGORY_SKILL.get(category, category) not in have:
        return 0.0
    # deeper bench = techs whose skill list is short (specialists)
    return round(1.0 / len(have) + 0.5, 2)


def dispatch(conn: sqlite3.Connection, wo_id: str) -> Assignment:
    wo = conn.execute(
        "SELECT category, unit_id, status FROM work_orders WHERE wo_id = ?",
        (wo_id,)).fetchone()
    if not wo:
        raise ValueError(f"unknown work order {wo_id}")
    category, unit_id, status = wo
    if status != "open":
        raise NotDispatchable(
            f"DSP-OPEN-01: {wo_id} is {status}; only open work orders are dispatched")
    bldg = conn.execute("SELECT building_id FROM units WHERE unit_id = ?",
                        (unit_id,)).fetchone()[0]

    cands = []
    at_max = 0
    for tech_id, _name, skills, home, shift, active in conn.execute(
            "SELECT tech_id, name, skills, home_building, shift, active_wos "
            "FROM technicians"):
        depth = _skill_depth(skills, category)
        if depth == 0.0:
            continue                      # skill hard filter
        if shift == "off":
            continue                      # off-shift techs excluded
        if active >= MAX_LOAD:
            at_max += 1
            continue                      # DSP-LOAD-01: never past max load
        proximity = 1.0 if home == bldg else 0.5
        load = min(active / MAX_LOAD, 1.0)
        score = round(0.40 * depth + 0.35 * proximity + 0.25 * (1 - load), 4)
        breakdown = (f"0.40*{depth}(skill) + 0.35*{proximity}(proximity) + "
                     f"0.25*{round(1 - load, 2)}(availability) = {score}")
        cands.append((score, tech_id, breakdown))

    if not cands:
        extra = f"; {at_max} qualified at max load (DSP-LOAD-01)" if at_max else ""
        raise NoTechAvailable(
            f"no qualified on-shift technician for {category} ({wo_id}){extra}")
    cands.sort(reverse=True)
    score, tech_id, breakdown = cands[0]
    conn.execute("UPDATE technicians SET active_wos = active_wos + 1 "
                 "WHERE tech_id = ?", (tech_id,))
    conn.execute("UPDATE work_orders SET status = 'assigned' WHERE wo_id = ?",
                 (wo_id,))
    conn.commit()
    return Assignment(wo_id, tech_id, score, breakdown)
