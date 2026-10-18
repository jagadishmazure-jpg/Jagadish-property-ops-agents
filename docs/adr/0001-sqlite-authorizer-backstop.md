# ADR 0001: SQLite authorizer backstop for the SELECT-only gateway

Date: 2026-10-18
Status: Accepted (implemented in `propops/authz.py`, `propops/views.py`)

## Revision 2026-10-18 (grokbot-portfolio): strict, view-aware authorizer

The first version of this ADR allowed READ on the base tables behind the
views outright, on the premise that denying them would break every view
query. That premise was wrong: when SQLite reads a base table on behalf of
a view, the authorizer's fifth argument names that view. The old rule made
the text check the only thing between a caller and the raw tables, and the
text check had gaps in principle (none found in this repo's denylist).

`propops/authz.py` now applies the portfolio template rule:

- A base-table READ is allowed only when the view-name argument is one of
  the published views. A READ with no view name is a direct read and is
  denied, whatever the query text looks like (comma joins, quoting,
  brackets, parentheses, comments, `main.` prefixes).
- `sqlite_master` / `sqlite_schema` are always denied, even if a caller
  lists them as allowed; `load_extension`, writes, DDL, PRAGMA and ATTACH
  are denied.
- One narrow exception: SQLite reports a read with an empty column name
  and no view name for a table that supplies no columns (one side of a
  view self-join). It is allowed only for tables that sit behind an
  allowed view, so `SELECT count(*) FROM <such table>` still returns a
  row count. Any column access (a `WHERE` on a base column) is denied.
- The text check stays as a first filter with readable errors.

`tests/test_authorizer_strict.py` runs the direct-read shapes against the
authorizer alone and through the gateway with the text check switched off.

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
