"""Fixed-template text-to-SQL over the four read-only views.

One simplified repair retry on GatewayError, then EscalationNeeded.
Never echoes raw row data in error messages.
"""

from __future__ import annotations

import re
import sqlite3

from .views import run_query, GatewayError


class EscalationNeeded(Exception):
    """Raised when the request cannot be answered safely."""


_INTENTS = [
    ("open_wos_by_priority",
     re.compile(r"(open|outstanding).*(work order|wo)s?.*(priorit|P1|urgent)|"
                r"(P1|P2|P3|P4).*(work order|wo)", re.I),
     "SELECT wo_id, building_id, unit_id, category, urgency, priority, status "
     "FROM v_open_wos ORDER BY urgency DESC"),
    ("tech_utilization",
     re.compile(r"(technician|tech).*(utili|load|busy|available)|"
                r"who.*(available|free)", re.I),
     "SELECT tech_id, name, skills, shift, active_wos "
     "FROM v_tech_utilization ORDER BY active_wos ASC"),
    ("overdue_preventive",
     re.compile(r"(overdue|late|missed).*(preventive|maintenance|pm)|"
                r"preventive.*(due|overdue)", re.I),
     "SELECT task_id, building_name, asset, due_date, days_overdue "
     "FROM v_preventive_overdue ORDER BY days_overdue DESC"),
    ("repeat_issues",
     re.compile(r"(repeat|recurring|again).*(issue|problem|work order)|"
                r"same.*unit.*(again|multiple)", re.I),
     "SELECT unit_id, category, COUNT(*) AS wo_count "
     "FROM v_open_wos GROUP BY unit_id, category HAVING wo_count >= 2"),
    ("satisfaction_trends",
     re.compile(r"(satisfaction|tenant).*(trend|score|rating)|"
                r"how.*(satisfied|happy).*tenant", re.I),
     "SELECT building_name, month, avg_score, responses "
     "FROM v_satisfaction ORDER BY month, avg_score ASC"),
]


def answer(conn: sqlite3.Connection, question: str) -> dict:
    """Answer a question; repair once, then escalate."""
    for name, pattern, template in _INTENTS:
        if pattern.search(question):
            try:
                rows = run_query(conn, template)
            except GatewayError:
                # one simplified repair: strip to the bare template
                try:
                    rows = run_query(conn, re.sub(r"\s+ORDER BY.*", "", template,
                                                 flags=re.I))
                except GatewayError as exc:
                    raise EscalationNeeded(
                        f"[{exc.rule_id}] could not run safe query") from exc
            return {"intent": name, "rows": rows, "count": len(rows)}
    raise EscalationNeeded("no matching intent; needs a human dispatcher")
