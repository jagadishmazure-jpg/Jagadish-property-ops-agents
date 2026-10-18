# Jagadish-property-ops-agents

End-to-end property maintenance operations agents: work-order triage,
technician dispatch, preventive maintenance, and tenant satisfaction —
on a fictional portfolio (Pellcrest Property Group), synthetic SQLite
telemetry, and a regression suite whose count CI checks.

**Recruiter summary.** Property teams drown in maintenance tickets and
miss the safety-critical ones. This repo shows an agent system that
triages every work order with a cited rule (urgency × tenant impact ×
asset criticality → P1–P4), dispatches the best qualified technician
with a per-factor breakdown, and refuses or gates anything risky —
behind a SELECT-only SQL gateway, a hash-chained audit log, and
PII-scrubbed feedback. The test count and the differentiator output in
"Standardization review" are regenerated and checked by CI on every push.

## How this differs from coldchain/retail

The cold-chain repo optimizes reefer telemetry and compliance; the
retail repo optimizes store operations. This repo is a **trust and
habitability** problem: the cost of a wrong answer is a tenant without
heat or an unqualified tech at a gas leak. So the differentiators are
different — a triage engine whose every decision cites its rule, and a
dispatch optimizer where skill is a hard filter (never a weight) and the
system raises `NoTechAvailable` instead of guessing. Eviction and
utility-shutoff requests are refused before any tool runs.

## Architecture

See [`knowledge/architecture.md`](knowledge/architecture.md) (Mermaid) and
[`knowledge/domain-notes.md`](knowledge/domain-notes.md) for the domain
background.

## How it works

1. **Seed** — `propops/telemetry.py` builds the synthetic portfolio:
   3 buildings, 264 units, 5 technicians, 30 work orders, preventive
   tasks, satisfaction surveys (seed 42, deterministic).
2. **Ask** — `text2sql.py` maps questions to 5 fixed intents over 4
   read-only views; the gateway (`views.py`) enforces SELECT-only with
   cited rule IDs (SEC-SELECT-01/02/03), one repair retry, then
   `EscalationNeeded`.
3. **Triage** — `triage.py` scores each work order and cites the rule:
   safety auto-P1 (TR-P1-02), repeat issues bumped a level (TR-ESC-01).
4. **Dispatch** — `dispatch.py` hard-filters on skill, then ranks by
   skill depth + proximity + availability with a published breakdown.
5. **Retrieve** — `sop_rag.py` does TF-IDF over the 4 SOPs with
   `file §section` citations; misses are explicit, never filled in.
6. **Signal** — `partssignal.py` quotes fake lead times in demo mode;
   the live stub raises `SignalGap`, reported verbatim.
7. **Guard** — T1–T4 escalation, confirmation gates on emergency
   dispatch and lease-violation enforcement (deny on timeout),
   hash-chained audit, PII scrubbing before feedback storage.

## Real excerpts, real output

Triage (from a real run):
```
WO-1001 -> P1 4.8 | 0.5*5(urgency) + 0.3*5.0(tenant-impact) + 0.2*4.0(asset-criticality) = 4.8
WO-1007 -> P1 4.7 | 0.5*5(urgency) + 0.3*4.0(tenant-impact) + 0.2*5.0(asset-criticality) = 4.7
WO-1002 -> P4 1.7 | 0.5*1(urgency) + 0.3*2.0(tenant-impact) + 0.2*3.0(asset-criticality) = 1.7
WO-1012 -> P2 3.0 | 0.5*3(urgency) + 0.3*3.0(tenant-impact) + 0.2*3.0(asset-criticality) = 3.0
```
WO-1007 is a gas-odor report: safety auto-P1 via TR-P1-02. WO-1012 was
P3 on urgency alone, bumped to P2 by TR-ESC-01 (third plumbing ticket in
the same unit within 30 days).

Dispatch (from a real run):
```
dispatch WO-1001 -> TECH-001 0.95
breakdown: 0.40*1.0(skill) + 0.35*1.0(proximity) + 0.25*0.8(availability) = 0.95
```

Text-to-SQL (from a real run):
```
"Which open work orders are P1?" -> intent: open_wos_by_priority, 0 rows, untriaged: 24
(after triaging WO-1001: 1 row, untriaged: 23)
```

SOP retrieval (from a real run):
```
"emergency dispatch confirmation" -> sop-02-dispatch.md §Technician dispatch (score 5.609)
```

## How to run

Offline first — stdlib only, no network, no keys:
```bash
python -m pytest tests/ -q        # full suite
python scripts/count_tests.py     # prints the real total
```

Optional demo UI:
```bash
pip install streamlit
streamlit run demo/app.py
```

## Guardrails and security controls

- SELECT-only gateway: single SELECT, no stacked statements or comments,
  no DDL/DML keywords outside string literals, only the four published
  views — raw base tables and `sqlite_master` rejected
  (SEC-SELECT-01/02/03, each with regression checks).
- SQLite authorizer (`propops/authz.py`), independent of the text check:
  a base table is readable only on behalf of a published view, never when
  named directly; `sqlite_master`, writes, PRAGMA/ATTACH and
  `load_extension` are denied. Rows are capped at 100 with `fetchmany`
  (the caller's `limit` is clamped), never `fetchall`.
  See [`docs/adr/0001-sqlite-authorizer-backstop.md`](docs/adr/0001-sqlite-authorizer-backstop.md).
- Confirmation gate on emergency dispatch and lease-violation
  enforcement; denies on timeout.
- Eviction / utility-shutoff requests refused before any tool runs.
- Hash-chained audit log (`verify_chain()`); entries capped at 500 chars
  and never echo raw row data.
- Feedback free text PII-scrubbed (email/phone/SSN/card) **before**
  storage; redaction counts kept.
- See [`SECURITY.md`](SECURITY.md) and
  [`docs/threat-model.md`](docs/threat-model.md).

## Limitations and known failures

- TF-IDF has no stemming: "triage" will not match "triaged". Queries
  should use the SOPs' vocabulary; a miss returns an explicit gap.
- Gateway: the authorizer's one allowance is an empty-column read of a
  table behind a view (needed for view self-joins), so
  `SELECT count(*) FROM work_orders` returns a count if the text check is
  bypassed; no column data is readable. See
  [`docs/adr/0001-sqlite-authorizer-backstop.md`](docs/adr/0001-sqlite-authorizer-backstop.md)
  and `tests/test_gateway_backstop.py`.
- The triage weights (0.5/0.3/0.2) and dispatch weights (0.40/0.35/0.25)
  are reasonable defaults, not calibrated — tune against historical
  tickets before production use.
- The live parts feed is a stub; only the fake feed returns lead times.
- Safety work orders (gas odor, sparking) are never auto-dispatched: no
  technician carries a safety skill, so dispatch raises `NoTechAvailable`
  and a human routes them.
- Priorities exist only for triaged work orders; priority questions report
  the untriaged count instead of guessing.
- The score bands (4.5 / 3.5 / 2.5) are as uncalibrated as the weights.
- Synthetic data only: 30 work orders cannot prove real-world triage
  quality. The 89 checks are regression checks, not quality claims.

## Standardization review (2026-10-18)

grokbot-portfolio reviewed this repo against the portfolio standard. Each
bug below has a regression test (`tests/test_propops.py`, "review fixes"
section, and `tests/test_authorizer_strict.py`) that fails on the old code.

- **Authorizer allowed raw base tables.** `authz.py` allowed READ on every
  table behind a view, so the text denylist was the only control; with it
  bypassed, `SELECT * FROM work_orders, v_open_wos` returned 720 rows. The
  authorizer now allows a base-table read only on behalf of a published
  view (ADR 0001, revision). The caller's `limit` is clamped to 100.
- **Repeat bump counted later tickets.** TR-ESC-01 counted tickets reported
  *after* the one being triaged, so WO-1010, the first of three plumbing
  tickets in unit U014, was bumped as a repeat. Only earlier tickets in
  the 30 days before now count.
- **The weighted score never affected the priority.** SOP-01 says the
  score maps to P1-P4, but only the rule ladder decided. The priority is
  now the higher of the ladder and the score band TR-SCORE-01, so 30
  residents without heat at urgency 3 (score 3.6) is P2, not P3.
- **Three categories could never be dispatched.** Appliance tickets needed
  a skill called "appliance" (technicians have "appliances") and
  structural tickets a "structural" skill nobody has. They now map to
  appliances and carpentry. Safety tickets still are not auto-dispatched
  and say so (no technician carries a safety skill).
- **Dispatch reopened closed work orders** (WO-1016, WO-1019 became
  "assigned") and double-assigned assigned ones. Only open work orders are
  dispatched now (DSP-OPEN-01).
- **A technician at maximum load was still assigned,** against SOP-02.
  Such technicians are skipped (DSP-LOAD-01).
- **The P1 emergency-dispatch gate could be skipped**: `dispatch_tech`
  only checked it for work orders triaged earlier in the same session.
  It now triages first, so an untriaged P1 is gated.
- **"Which open work orders are P1?" returned all 24 open work orders,**
  none of which had a priority. The intent now filters by the priority
  named and reports how many open work orders are still untriaged.
- **The card pattern redacted dates and unit numbers** (`2026-10-18
  2026-10-25` became `[CARD]-25`). It now matches 4x4 groups or 13-16
  contiguous digits only.
- Fictional names that matched real businesses were renamed
  (the company is now Pellcrest Property Group).

Differentiator on the seeded data (regenerated and checked by CI on every push):

<!-- run: python scripts/show_differentiator.py -->
```text
Triage (priority = higher of rule ladder and score band; repeat bump last):
  WO-1001 -> P1 4.8 | TR-P1-01
  WO-1007 -> P1 4.7 | TR-P1-02
  WO-1010 -> P3 3.0 | TR-P3-01
  WO-1011 -> P4 2.2 | TR-P4-01
  WO-1012 -> P2 3.0 | TR-P3-01; TR-ESC-01
  WO-1016 -> P3 2.5 | TR-P4-01; TR-SCORE-01
  WO-1032 -> P2 2.2 | TR-P2-01
Dispatch (skill hard filter, open work orders only, max load respected):
  WO-1001 -> TECH-001 | 0.40*1.0(skill) + 0.35*1.0(proximity) + 0.25*0.8(availability) = 0.95
  WO-1018 -> TECH-003 | 0.40*1.0(skill) + 0.35*0.5(proximity) + 0.25*1.0(availability) = 0.825
  WO-1029 -> TECH-002 | 0.40*1.0(skill) + 0.35*0.5(proximity) + 0.25*0.4(availability) = 0.675
  WO-1007 -> not dispatched: no qualified on-shift technician for safety (WO-1007)
  WO-1016 -> not dispatched: DSP-OPEN-01: WO-1016 is closed; only open work orders are dispatched
Emergency dispatch of untriaged P1 WO-1001: human confirmation required and not granted for emergency_dispatch
Gateway: SELECT * FROM v_open_wos, work_orders -> [SEC-SELECT-03] raw table access is not allowed; use the published views
```
<!-- /run -->

Test count (also checked by CI):

<!-- run: python scripts/count_tests.py -->
```text
121 tests collected
```
<!-- /run -->

## Built / Written-not-run / Planned

| Item | Status |
|---|---|
| Triage engine + dispatch optimizer, gateway, RAG, signals, orchestrator, audit, PII-scrubbed feedback | Built (test count above) |
| Thin Streamlit demo (`demo/app.py`) | Built, logic tested via `demo_helpers` |
| `knowledge/` docs, SOPs, implementation guide, interview points, threat model | Built |
| CI: ruff, pytest, docs drift check, hashed brand check, gitleaks; CodeQL; Dependabot | Built (runs on every push) |
| Live parts-supplier integration | Planned |
| Calibration of triage/dispatch weights on historical tickets | Planned |
| Deployment to any cloud | Planned (nothing deployed) |

## Related repos

- `Jagadish-coldchain-logistics-agents` — the FDE spine this repo follows
  (reefer telemetry; different differentiators).
- `Jagadish-retail-ops-agents` — same spine (store operations).
- `Jagadish-warehouse-ops-agents` — same spine (slotting optimizer).
- `Jagadish-energy-grid-agents` — also ranks field crews, but for grid
  outages (critical-facility severity floor, utility crews). This repo
  dispatches building technicians to tenant work orders with a
  category-to-skill map, a load cap and a P1 confirmation gate.
- `Jagadish-predictive-maintenance-agents` — predicts equipment failure
  from sensor trends. This repo's preventive tasks are calendar-based
  (overdue view); there is no failure prediction here.

---

*All data is synthetic and fictional (Pellcrest Property Group is an
invented name). This is an independent portfolio project, not affiliated
with any real property company.*
