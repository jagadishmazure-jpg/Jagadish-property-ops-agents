"""SQLite authorizer backstop for the SELECT-only gateway.

Registers ``conn.set_authorizer()`` so the database itself enforces the
read-only contract, behind the text-level checks in ``views.py``.

What the authorizer enforces:
  * Only SELECT statements may run (denies INSERT/UPDATE/DELETE, DDL,
    PRAGMA, ATTACH/DETACH, and every other action code).
  * READ is allowed on the published views and on the base tables those
    views are defined over — and denied on everything else, including
    ``sqlite_master`` / ``sqlite_sequence``.

Why the base tables are allowlisted: SQLite invokes the authorizer for
base tables referenced *inside* view definitions (verified empirically:
``SELECT * FROM v`` triggers ``SQLITE_READ`` on the view's underlying
tables as well as on the view). Denying base-table reads would break
every legitimate view query, so the authorizer cannot be the layer that
blocks raw ``FROM work_orders`` — that is the text-level denylist's job
(``SEC-SELECT-03`` in ``views.py``). The authorizer is defense-in-depth:
it catches what text checks can miss — quoted system tables
(``FROM "sqlite_master"``), ``PRAGMA``, ``ATTACH``, and writes smuggled
past the keyword scan.

The authorizer is active only inside the ``views_only`` context (used by
``views.run_query``). Engines (triage/dispatch) use the same connection
for parameterized writes, so the authorizer must never leak past the
planner call — the context manager always clears it on exit.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterable


@contextmanager
def views_only(conn: sqlite3.Connection,
               allowed_views: Iterable[str],
               allowed_tables: Iterable[str]):
    """Yield ``conn`` with a view-only authorizer registered.

    ``allowed_views``: the published ``v_*`` view names.
    ``allowed_tables``: base tables the views are defined over (required
    for view queries to execute; see module docstring).
    Denied access raises ``sqlite3.DatabaseError`` from the driver.
    """
    views = {v.lower() for v in allowed_views}
    tables = {t.lower() for t in allowed_tables}

    def _authorizer(action: int, arg1: str | None, arg2: str | None,
                    dbname: str | None, trigger: str | None) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            name = (arg1 or "").lower()
            if name in views or name in tables:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            # Aggregate/scalar functions (count, avg, julianday, ...) over
            # allowlisted reads are harmless; table access is still gated.
            return sqlite3.SQLITE_OK
        # Deny everything else: writes, DDL, PRAGMA, ATTACH, ...
        return sqlite3.SQLITE_DENY

    conn.set_authorizer(_authorizer)
    try:
        yield conn
    finally:
        conn.set_authorizer(None)
