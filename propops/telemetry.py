"""Synthetic property telemetry on SQLite.

Fictional portfolio: Harborview Property Group (invented). Deterministic
seed (42). Anchor records the tests rely on:

  * WO-1001 — burst water main, urgency 5, 40 residents affected -> P1
  * WO-1002 — dripping faucet, urgency 1 -> P4
  * WO-1007 — gas odor report -> safety auto-P1
  * TECH-001 — plumbing skill, home BLDG-01, day shift
  * PM-201  — elevator preventive task, overdue
  * U-014   — three plumbing WOs in 30 days (repeat-issue anchor)
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE buildings (
    building_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    units INTEGER NOT NULL
);
CREATE TABLE units (
    unit_id TEXT PRIMARY KEY,
    building_id TEXT NOT NULL REFERENCES buildings(building_id),
    floor INTEGER NOT NULL,
    bedrooms INTEGER NOT NULL
);
CREATE TABLE technicians (
    tech_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    skills TEXT NOT NULL,          -- comma-separated
    home_building TEXT NOT NULL REFERENCES buildings(building_id),
    shift TEXT NOT NULL,           -- day | night | off
    active_wos INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE work_orders (
    wo_id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL REFERENCES units(unit_id),
    category TEXT NOT NULL,        -- plumbing|electrical|hvac|appliance|structural|pest|safety
    summary TEXT NOT NULL,
    urgency INTEGER NOT NULL,      -- 1..5
    residents_affected INTEGER NOT NULL DEFAULT 1,
    asset TEXT,                    -- affected asset, e.g. boiler, elevator
    status TEXT NOT NULL,          -- open|assigned|in_progress|closed
    priority TEXT,                 -- P1..P4 once triaged
    reported_at TEXT NOT NULL
);
CREATE TABLE preventive (
    task_id TEXT PRIMARY KEY,
    building_id TEXT NOT NULL REFERENCES buildings(building_id),
    asset TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL           -- scheduled|overdue|done
);
CREATE TABLE satisfaction (
    survey_id TEXT PRIMARY KEY,
    building_id TEXT NOT NULL REFERENCES buildings(building_id),
    month TEXT NOT NULL,           -- YYYY-MM
    score INTEGER NOT NULL         -- 1..5
);
"""

BUILDINGS = [
    ("BLDG-01", "Harborview Tower A", 120),
    ("BLDG-02", "Harborview Tower B", 96),
    ("BLDG-03", "Marina Court", 48),
]

TECHS = [
    ("TECH-001", "A. Rivera", "plumbing,hvac", "BLDG-01", "day", 1),
    ("TECH-002", "B. Okafor", "electrical,appliances", "BLDG-01", "day", 3),
    ("TECH-003", "C. Novak", "carpentry,plumbing", "BLDG-02", "day", 0),
    ("TECH-004", "D. Kim", "hvac,electrical", "BLDG-02", "night", 2),
    ("TECH-005", "E. Haddad", "pest,carpentry", "BLDG-03", "day", 1),
]


def seed(rng: random.Random | None = None) -> sqlite3.Connection:
    rng = rng or random.Random(42)
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)

    conn.executemany(
        "INSERT INTO buildings VALUES (?,?,?)", BUILDINGS)
    units = []
    for bldg, _, count in BUILDINGS:
        for i in range(count):
            uid = f"{bldg}-U{i + 1:03d}"
            units.append((uid, bldg, rng.randint(1, 20), rng.choice([1, 2, 3])))
    conn.executemany("INSERT INTO units VALUES (?,?,?,?)", units)
    conn.executemany("INSERT INTO technicians VALUES (?,?,?,?,?,?)", TECHS)

    base = datetime(2026, 10, 1, 9, 0, 0)
    wos = [
        # --- deterministic anchors ---
        ("WO-1001", "BLDG-01-U012", "plumbing", "Burst water main, lobby flooding",
         5, 40, "water-main", "open", None,
         (base - timedelta(hours=2)).isoformat()),
        ("WO-1002", "BLDG-01-U045", "plumbing", "Dripping bathroom faucet",
         1, 1, None, "open", None,
         (base - timedelta(days=1)).isoformat()),
        ("WO-1007", "BLDG-02-U007", "safety", "Gas odor reported near boiler room",
         5, 12, "boiler", "open", None,
         (base - timedelta(hours=1)).isoformat()),
        # repeat-issue anchor: three plumbing WOs in U-014 within 30 days
        ("WO-1010", "BLDG-01-U014", "plumbing", "Clogged kitchen drain",
         3, 2, None, "open", None,
         (base - timedelta(days=20)).isoformat()),
        ("WO-1011", "BLDG-01-U014", "plumbing", "Slow bathroom drain",
         2, 1, None, "open", None,
         (base - timedelta(days=11)).isoformat()),
        ("WO-1012", "BLDG-01-U014", "plumbing", "Gurgling pipes, possible blockage",
         3, 2, None, "open", None,
         (base - timedelta(days=2)).isoformat()),
    ]
    cats = ["electrical", "hvac", "appliance", "structural", "pest"]
    summaries = {
        "electrical": "Outlet sparking in bedroom",
        "hvac": "AC not cooling below 78F",
        "appliance": "Dishwasher not draining",
        "structural": "Crack in hallway drywall",
        "pest": "Ants in kitchen pantry",
    }
    n = 1013
    for i in range(24):
        bldg = rng.choice(BUILDINGS)[0]
        unit = f"{bldg}-U{rng.randint(1, 40):03d}"
        cat = rng.choice(cats)
        wos.append((
            f"WO-{n}", unit, cat, summaries[cat],
            rng.randint(1, 4), rng.randint(1, 4),
            rng.choice([None, "boiler", "elevator", "roof"]),
            rng.choice(["open", "assigned", "in_progress", "closed"]),
            None,
            (base - timedelta(days=rng.randint(0, 25),
                               hours=rng.randint(0, 23))).isoformat(),
        ))
        n += 1
    conn.executemany(
        "INSERT INTO work_orders VALUES (?,?,?,?,?,?,?,?,?,?)", wos)

    pm = [
        ("PM-201", "BLDG-01", "elevator",
         (base - timedelta(days=9)).date().isoformat(), "overdue"),
        ("PM-202", "BLDG-02", "boiler",
         (base + timedelta(days=5)).date().isoformat(), "scheduled"),
        ("PM-203", "BLDG-03", "roof",
         (base - timedelta(days=3)).date().isoformat(), "overdue"),
        ("PM-204", "BLDG-01", "fire-alarm",
         (base - timedelta(days=30)).date().isoformat(), "done"),
    ]
    conn.executemany("INSERT INTO preventive VALUES (?,?,?,?,?)", pm)

    surv = []
    sid = 1
    for bldg, _, _ in BUILDINGS:
        for m in range(1, 4):
            for _ in range(12):
                surv.append((f"S-{sid}", bldg, f"2026-{m:02d}",
                             rng.randint(2, 5)))
                sid += 1
    conn.executemany("INSERT INTO satisfaction VALUES (?,?,?,?)", surv)

    conn.commit()
    return conn
