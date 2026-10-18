"""Deterministic demo helpers — all Streamlit logic lives here and is tested.

demo/app.py only imports these lazily and renders; no logic in the UI file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import dispatch as dispatch_mod
from . import telemetry
from . import text2sql as t2s
from . import triage as triage_mod
from .views import install_views

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "sops"


def get_conn() -> sqlite3.Connection:
    conn = telemetry.seed()
    install_views(conn)
    return conn


def triage_work_order(conn: sqlite3.Connection, wo_id: str) -> dict:
    d = triage_mod.triage(conn, wo_id)
    return {"wo_id": d.wo_id, "priority": d.priority, "score": d.score,
            "breakdown": d.breakdown, "rules": d.rules}


def dispatch_for(conn: sqlite3.Connection, wo_id: str) -> dict:
    try:
        a = dispatch_mod.dispatch(conn, wo_id)
    except (dispatch_mod.NoTechAvailable, dispatch_mod.NotDispatchable) as exc:
        return {"dispatched": False, "reason": str(exc)}
    return {"dispatched": True, "tech_id": a.tech_id, "score": a.score,
            "breakdown": a.breakdown}


def ask(conn: sqlite3.Connection, question: str) -> dict:
    try:
        return t2s.answer(conn, question)
    except t2s.EscalationNeeded as exc:
        return {"escalated": True, "reason": str(exc)}


def open_wo_summary(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(
        "SELECT priority, COUNT(*) AS n FROM work_orders "
        "WHERE status != 'closed' GROUP BY priority")]
