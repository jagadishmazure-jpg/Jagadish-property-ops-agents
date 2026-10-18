"""Regression tests for the SQLite gateway backstop (issue #8 fix).

Each test covers one bypass shape that defeated the text-only gateway:
comma joins, quoted system tables, comment-whitespace, LIMIT tricks, and
raw base-table names. The database authorizer (propops.authz) is the
backstop behind the text checks.
"""

import sqlite3

import pytest

from propops import pii, telemetry, views
from propops.authz import views_only
from propops.views import GatewayError


@pytest.fixture()
def conn():
    c = telemetry.seed()
    views.install_views(c)
    return c


@pytest.fixture()
def big_conn():
    """Connection with >100 open work orders for cap tests."""
    c = telemetry.seed()
    views.install_views(c)
    for i in range(150):
        c.execute(
            "INSERT INTO work_orders (wo_id, unit_id, category, summary, "
            "urgency, residents_affected, status, reported_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (f"WO-B{i}", "BLDG-01-U001", "plumbing", "t", 1, 1, "open",
             "2026-10-18"))
    c.commit()
    return c


# ---------- bypass: raw base table ----------

def test_backstop_rejects_raw_table(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "SELECT * FROM work_orders")
    assert e.value.rule_id == "SEC-SELECT-03"


# ---------- bypass: comma join ----------

def test_backstop_rejects_comma_join(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "SELECT * FROM v_open_wos, work_orders")
    assert e.value.rule_id == "SEC-SELECT-03"


# ---------- bypass: quoted sqlite_master ----------

def test_backstop_rejects_quoted_sqlite_master(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, 'SELECT * FROM "sqlite_master"')
    assert e.value.rule_id == "SEC-SELECT-03"


def test_authorizer_denies_sqlite_master_directly(conn):
    with views_only(conn, views.VIEWS.keys(), views.BASE_TABLES):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute('SELECT * FROM "sqlite_master"').fetchall()


# ---------- bypass: comment-whitespace ----------

def test_backstop_rejects_comment_whitespace(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "SELECT * FROM/**/work_orders")
    assert e.value.rule_id == "SEC-SELECT-02"


# ---------- bypass: LIMIT tricks (fetchmany cap, never trust LIMIT) ----------

def test_backstop_caps_limit_100000(big_conn):
    rows = views.run_query(big_conn, "SELECT * FROM v_open_wos LIMIT 100000")
    assert len(rows) == 100


def test_backstop_caps_limit_offset(big_conn):
    rows = views.run_query(big_conn,
                           "SELECT * FROM v_open_wos LIMIT 50 OFFSET 120")
    assert len(rows) <= 100


def test_backstop_rejects_limit_comment(big_conn):
    # The retail bypass shape: comment smuggles a huge LIMIT past rewriting.
    with pytest.raises(GatewayError) as e:
        views.run_query(big_conn, "SELECT * FROM v_open_wos LIMIT 100000 -- x")
    assert e.value.rule_id == "SEC-SELECT-02"


def test_backstop_never_fetchall(big_conn):
    # Even a query with no LIMIT at all is capped at fetch time.
    rows = views.run_query(big_conn, "SELECT * FROM v_open_wos")
    assert len(rows) == 100


# ---------- authorizer: views still work, writes/PRAGMA denied ----------

def test_authorizer_allows_view_aggregates(conn):
    with views_only(conn, views.VIEWS.keys(), views.BASE_TABLES):
        row = conn.execute("SELECT count(*) FROM v_open_wos").fetchone()
    assert row[0] > 0


def test_authorizer_denies_write_and_pragma(conn):
    with views_only(conn, views.VIEWS.keys(), views.BASE_TABLES):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE work_orders SET priority='P1'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("PRAGMA table_info(work_orders)").fetchall()
    # Authorizer is cleared on context exit: engines can write again.
    conn.execute("UPDATE work_orders SET priority='P4' WHERE wo_id='WO-1001'")
    conn.commit()


def test_authorizer_denial_maps_to_sec_select_03(conn, monkeypatch):
    # Force the authorizer path by smuggling past text checks is not
    # possible; instead verify a denied DB operation surfaces as
    # SEC-SELECT-03 when it happens inside run_query.
    orig = views.views_only

    def deny_all(c, v, t):
        return views_only(c, set(), set())

    monkeypatch.setattr(views, "views_only", deny_all)
    try:
        with pytest.raises(GatewayError) as e:
            views.run_query(conn, "SELECT wo_id FROM v_open_wos")
        assert e.value.rule_id == "SEC-SELECT-03"
    finally:
        monkeypatch.setattr(views, "views_only", orig)


# ---------- PII: phone formats redacted, dates intact ----------

@pytest.mark.parametrize("raw", [
    "(555) 123-4567",
    "+1 (555) 123-4567",
    "555.123.4567",
    "555-123-4567",
])
def test_pii_redacts_phone_formats(raw):
    scrubbed, n = pii.scrub(f"call {raw} now")
    assert "[PHONE]" in scrubbed and raw not in scrubbed and n == 1


def test_pii_redacts_ssn():
    scrubbed, n = pii.scrub("ssn 123-45-6789 here")
    assert "[SSN]" in scrubbed and n == 1


@pytest.mark.parametrize("raw", [
    "2026-10-18",
    "Meeting on 2026-10-18 at 3pm",
    "due 2026-01-05",
])
def test_pii_keeps_dates_intact(raw):
    scrubbed, n = pii.scrub(raw)
    assert scrubbed == raw and n == 0
