"""Read-only SQL views + SELECT-only gateway.

Rule IDs (cited in audit + errors):
  SEC-SELECT-01 — only a single SELECT statement is allowed.
  SEC-SELECT-02 — no stacked statements, comments, or DDL/DML keywords
                  outside string literals.
  SEC-SELECT-03 — queries may only touch the four published views; raw
                  base tables and system tables are rejected.

Defense in depth: the text checks below are the primary gate. Behind
them, ``authz.views_only`` registers a SQLite authorizer on the
connection so the database itself denies writes, PRAGMA/ATTACH, and
reads of sqlite_master. Row counts are capped with ``fetchmany`` —
never by trusting the query's LIMIT.
"""

from __future__ import annotations

import re
import sqlite3

from .authz import views_only

VIEWS = {
    "v_open_wos": """
        CREATE VIEW v_open_wos AS
        SELECT w.wo_id, u.building_id, w.unit_id, w.category, w.summary,
               w.urgency, w.residents_affected, w.asset, w.status,
               w.priority, w.reported_at
        FROM work_orders w JOIN units u ON u.unit_id = w.unit_id
        WHERE w.status != 'closed'
    """,
    "v_tech_utilization": """
        CREATE VIEW v_tech_utilization AS
        SELECT t.tech_id, t.name, t.skills, t.home_building, t.shift,
               t.active_wos,
               (SELECT COUNT(*) FROM work_orders w
                 WHERE w.status IN ('assigned','in_progress')) AS open_wos
        FROM technicians t
    """,
    "v_preventive_overdue": """
        CREATE VIEW v_preventive_overdue AS
        SELECT p.task_id, p.building_id, b.name AS building_name,
               p.asset, p.due_date, p.status,
               CAST(julianday('2026-10-18') - julianday(p.due_date) AS INTEGER)
                 AS days_overdue
        FROM preventive p JOIN buildings b ON b.building_id = p.building_id
        WHERE p.status = 'overdue'
    """,
    "v_satisfaction": """
        CREATE VIEW v_satisfaction AS
        SELECT s.building_id, b.name AS building_name, s.month,
               ROUND(AVG(s.score), 2) AS avg_score,
               COUNT(*) AS responses
        FROM satisfaction s JOIN buildings b ON b.building_id = s.building_id
        GROUP BY s.building_id, s.month
    """,
}

_WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|grant|revoke|attach|detach)\b",
    re.IGNORECASE,
)

# Base tables the views are defined over. Passed to the authorizer as
# the table allowlist (SQLite invokes the authorizer for base tables
# inside view definitions, so views cannot run without this).
BASE_TABLES = {
    "work_orders", "units", "technicians", "buildings",
    "preventive", "satisfaction",
}

# System tables are never allowlisted anywhere: mentioning them in
# planner SQL is rejected here, and the authorizer denies them too.
_SYSTEM_TABLES = {"sqlite_master", "sqlite_sequence", "sqlite_temp_master"}

_TABLE_DENY = re.compile(
    r"\b(work_orders|units|technicians|buildings|preventive|satisfaction"
    r"|sqlite_master|sqlite_sequence|sqlite_temp_master)\b",
    re.IGNORECASE,
)


def _strip_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def _normalize_identifiers(sql: str) -> str:
    """Strip string literals, then unquote "..."/[...]/`...` identifiers.

    Lets the table denylist catch quoted variants such as
    ``FROM "sqlite_master"`` or ``FROM [work_orders]``.
    """
    sql = _strip_literals(sql)
    sql = re.sub(r'"([^"]+)"', r"\1", sql)
    sql = re.sub(r"\[([^\]]+)\]", r"\1", sql)
    sql = re.sub(r"`([^`]+)`", r"\1", sql)
    return sql


class GatewayError(Exception):
    def __init__(self, rule_id: str, detail: str):
        super().__init__(f"[{rule_id}] {detail}")
        self.rule_id = rule_id


def install_views(conn: sqlite3.Connection) -> None:
    for ddl in VIEWS.values():
        conn.execute(ddl.replace("CREATE VIEW", "CREATE VIEW IF NOT EXISTS"))
    conn.commit()


def run_query(conn: sqlite3.Connection, sql: str, limit: int = 100) -> list[dict]:
    """Execute a read-only query after gateway checks.

    The row cap is enforced with ``fetchmany(limit + 1)`` — the query's
    own LIMIT is never trusted (``LIMIT 100000 -- x``, ``LIMIT n OFFSET
    m``, and ``LIMIT m, n`` all bypass LIMIT-rewriting). ``fetchall`` is
    never called on planner queries.
    """
    text = sql.strip().rstrip(";")
    if not re.match(r"(?is)^\s*select\b", text):
        raise GatewayError("SEC-SELECT-01", "only a single SELECT statement is allowed")
    if ";" in _strip_literals(text):
        raise GatewayError("SEC-SELECT-02", "stacked statements are not allowed")
    if re.search(r"--|/\*", _strip_literals(text)):
        raise GatewayError("SEC-SELECT-02", "comments are not allowed")
    if _WRITE_KEYWORDS.search(_strip_literals(text)):
        raise GatewayError("SEC-SELECT-02", "write/DDL keywords are not allowed")
    mentioned = set(re.findall(r"(?i)\bv_\w+", text))
    unknown = mentioned - set(VIEWS)
    if unknown:
        raise GatewayError("SEC-SELECT-03",
                           f"unknown views: {sorted(unknown)}")
    if _TABLE_DENY.search(_normalize_identifiers(text)):
        raise GatewayError("SEC-SELECT-03",
                           "raw table access is not allowed; use the published views")
    conn.row_factory = sqlite3.Row
    try:
        with views_only(conn, VIEWS.keys(), BASE_TABLES):
            cursor = conn.execute(text)
            rows = cursor.fetchmany(limit + 1)[:limit]
    except sqlite3.DatabaseError as exc:
        # Authorizer denial (or any other DB-level refusal).
        raise GatewayError("SEC-SELECT-03",
                           f"denied by database authorizer: {exc}") from exc
    except sqlite3.Error as exc:
        raise GatewayError("SEC-SELECT-01", f"query failed: {exc}") from exc
    return [dict(r) for r in rows]
