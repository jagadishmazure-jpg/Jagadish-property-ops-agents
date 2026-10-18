# ADR 0001: SQLite authorizer backstop for the SELECT-only gateway

Date: 2026-10-18
Status: Accepted (implemented in `propops/authz.py`, `propops/views.py`)

## Context

The planner's SQL gateway (`views.run_query`) enforced read-only access
with text checks:

- SEC-SELECT-01: single SELECT statement only.
- SEC-SELECT-02: no stacked statements, comments, or DDL/DML keywords
  outside string literals.
- SEC-SELECT-03: every mentioned `v_*` name must be a published view.

A sibling repo's review found real bypasses in this pattern. The sharpest
one: SEC-SELECT-03 only validated that *mentioned* `v_*` names were
known. A query naming **no** view at all — `SELECT * FROM work_orders` —
mentioned nothing to reject, so it sailed through and read the raw base
table, bypassing the views' column restrictions. Variants: comma joins
(`FROM v_open_wos, work_orders`), quoted system tables
(`FROM "sqlite_master"`), and comment-whitespace (`FROM/**/work_orders`).

A second, independent bypass: the row cap trusted the query's LIMIT.
`LIMIT 100000 -- x` returned 36,864 rows in the retail sibling.

## Decision

Defense in depth, three layers:

1. **Text denylist (primary).** `views.py` now rejects any mention of a
   base-table or system-table name — including `"quoted"`, `[bracketed]`,
   and `` `backticked` `` variants — with SEC-SELECT-03. Planner SQL may
   name only the four published views.

2. **SQLite authorizer backstop** (`propops/authz.py::views_only`).
   Registers `conn.set_authorizer()` for the duration of each planner
   query: allows SELECT + function calls + READ on the published views
   (and the base tables they are defined over — required, because SQLite
   invokes the authorizer for base tables referenced *inside* view
   definitions; verified empirically), denies READ on `sqlite_master` /
   `sqlite_sequence` / anything else, and denies writes, DDL, PRAGMA,
   and ATTACH. Denials surface as `sqlite3.DatabaseError`, mapped to
   SEC-SELECT-03. The authorizer is cleared on context exit so the
   engines (triage/dispatch), which share the connection and issue
   parameterized UPDATEs, are unaffected.

3. **Fetch-time row cap.** `run_query` uses
   `cursor.fetchmany(limit + 1)[:limit]` and never calls `fetchall()` on
   planner queries. The query's own LIMIT (`LIMIT 100000`,
   `LIMIT n OFFSET m`, `LIMIT m, n`, LIMIT in a subquery) is never
   trusted.

Engines (`triage.py`, `dispatch.py`) already read the database directly
with parameterized queries — never through the planner cap — so no row
is silently dropped there; no change was needed.

## Consequences

- Planner SQL is confined to the four views at two independent layers;
  a bypass must defeat both the text denylist and the authorizer.
- `tests/test_gateway_backstop.py` pins one regression test per bypass
  shape (20 tests).
- The authorizer adds negligible overhead (one callback per read) and is
  scoped to planner queries only.
