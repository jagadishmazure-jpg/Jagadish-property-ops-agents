"""Strict, view-aware authorizer (SEC-SELECT-03), tested independently of the text check.

A base-table READ is allowed only when SQLite reports it on behalf of an
allowed view (the authorizer's view-name argument). A READ naming the table
directly, with no view, is denied; sqlite_master is always denied.
"""

import re
import sqlite3

import pytest

from propops import views
from propops.authz import views_only

ALLOWED = list(views.VIEWS)

DIRECT_READS = [
    "SELECT * FROM work_orders, v_open_wos",
    "SELECT * FROM/**/\"work_orders\"/**/,/**/v_open_wos",
    "SELECT * FROM v_open_wos JOIN (work_orders) ON 1 = 1",
    "SELECT * FROM v_open_wos WHERE EXISTS (SELECT 1 FROM main.[work_orders] WHERE work_orders.rowid > 0)",
    "SELECT urgency FROM work_orders",
    "SELECT * FROM\"work_orders\"\t,\nv_open_wos",
]
# property-ops rejects comments up front (SEC-SELECT-02), so the gateway-level
# test there uses the comment-free variants.
GATEWAY_READS = [s for s in DIRECT_READS if "/*" not in s]


@pytest.fixture()
def conn():
    from propops import demo_helpers as dh
    return dh.get_conn()


@pytest.mark.parametrize("sql", DIRECT_READS)
def test_authorizer_denies_direct_base_table_reads(conn, sql):
    with views_only(conn, ALLOWED) as denied:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql).fetchall()
    assert "work_orders" in [d.lower() for d in denied]


@pytest.mark.parametrize("sql", GATEWAY_READS)
def test_gateway_denies_direct_reads_with_text_check_disabled(conn, monkeypatch, sql):
    monkeypatch.setattr(views, "_TABLE_DENY", re.compile(r"(?!x)x"))
    with pytest.raises(views.GatewayError, match="SEC-SELECT-03"):
        views.run_query(conn, sql)


def test_sqlite_master_is_denied_even_if_listed_as_allowed(conn):
    with views_only(conn, ALLOWED + ["sqlite_master"]):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute('SELECT name FROM "sqlite_master"').fetchall()


def test_load_extension_is_denied(conn):
    with views_only(conn, ALLOWED):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT load_extension('x') FROM v_open_wos").fetchall()


@pytest.mark.parametrize("view", ALLOWED)
def test_every_published_view_is_readable(conn, view):
    with views_only(conn, ALLOWED) as denied:
        conn.execute(f"SELECT * FROM {view}").fetchall()
    assert denied == []


def test_view_self_join_is_not_falsely_denied(conn):
    with views_only(conn, ALLOWED) as denied:
        conn.execute("SELECT count(*) FROM v_open_wos a JOIN v_open_wos b ON 1 = 1").fetchall()
    assert denied == []


def test_base_column_filter_is_denied_even_in_count(conn):
    # Documented residual: count(*) of a table behind a view reads no column.
    # Any column access (here a WHERE filter) is still denied.
    with views_only(conn, ALLOWED):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT count(*) FROM work_orders WHERE urgency > 0").fetchall()


# ---------- CodeQL fixes (grokbot-portfolio, 2026-10-18) ----------
def test_unquote_matches_regex_and_is_linear():
    import time

    from propops.views import _unquote
    for s in ['SELECT * FROM [work_orders]', '[a] [] [b', 'x [[y]] z', '"q" ""r"', '']:
        assert _unquote(s, "[", "]") == re.sub(r"\[([^\]]+)\]", r"\1", s)
        assert _unquote(s, '"', '"') == re.sub(r'"([^"]+)"', r"\1", s)
    t = time.perf_counter()
    _unquote("[" * 200_000, "[", "]")
    assert time.perf_counter() - t < 1.0


def test_drop_order_by():
    from propops.text2sql import _drop_order_by
    assert _drop_order_by("SELECT a FROM v_open_wos  ORDER BY a DESC") == "SELECT a FROM v_open_wos"
    assert _drop_order_by("SELECT a FROM v_open_wos") == "SELECT a FROM v_open_wos"
