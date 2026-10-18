"""Fixed-template text-to-SQL over the four read-only views.

One simplified repair retry on GatewayError, then EscalationNeeded.
Never echoes raw row data in error messages.
"""

from __future__ import annotations

import re
import sqlite3

from .views import GatewayError, run_query


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


_PRIORITY = re.compile(r"\bP([1-4])\b", re.I)



def _drop_order_by(sql: str) -> str:
    """Cut a trailing ORDER BY clause (linear; no backtracking regex)."""
    cut = sql.upper().find("ORDER BY")
    return sql if cut == -1 else sql[:cut].rstrip()

def _with_priority(name: str, template: str, question: str) -> str:
    """Filter open work orders by the priority the question names (P1..P4)."""
    m = _PRIORITY.search(question)
    if name != "open_wos_by_priority" or not m:
        return template
    return template.replace(" ORDER BY", f" WHERE priority = 'P{m.group(1)}' ORDER BY")


def answer(conn: sqlite3.Connection, question: str) -> dict:
    """Answer a question; repair once, then escalate.

    A question naming a priority (P1..P4) gets only work orders with that
    priority; the result also reports how many open work orders have not
    been triaged yet, so an empty answer is not mistaken for "none".
    """
    for name, pattern, template in _INTENTS:
        if pattern.search(question):
            template = _with_priority(name, template, question)
            try:
                rows = run_query(conn, template)
            except GatewayError:
                # one simplified repair: strip to the bare template
                try:
                    rows = run_query(conn, _drop_order_by(template))
                except GatewayError as exc:
                    raise EscalationNeeded(
                        f"[{exc.rule_id}] could not run safe query") from exc
            out = {"intent": name, "rows": rows, "count": len(rows)}
            if template.find("WHERE priority") != -1:
                out["untriaged"] = run_query(
                    conn, "SELECT COUNT(*) AS n FROM v_open_wos WHERE priority IS NULL")[0]["n"]
            return out
    raise EscalationNeeded("no matching intent; needs a human dispatcher")
