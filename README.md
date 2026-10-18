# Jagadish-property-ops-agents

End-to-end property maintenance operations agents: work-order triage,
technician dispatch, preventive maintenance, and tenant satisfaction —
on a fictional portfolio (Harborview Property Group), synthetic SQLite
telemetry, and 69 green regression checks.

**Recruiter summary.** Property teams drown in maintenance tickets and
miss the safety-critical ones. This repo shows an agent system that
triages every work order with a cited rule (urgency × tenant impact ×
asset criticality → P1–P4), dispatches the best qualified technician
with a per-factor breakdown, and refuses or gates anything risky —
behind a SELECT-only SQL gateway, a hash-chained audit log, and
PII-scrubbed feedback. Proof: 89/89 tests green, every README number
below from a real run.

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
"Which open work orders are P1?" -> intent: open_wos_by_priority, 24 rows
```

SOP retrieval (from a real run):
```
"emergency dispatch confirmation" -> sop-02-dispatch.md §Technician dispatch (score 5.609)
```

## How to run

Offline first — stdlib only, no network, no keys:
```bash
python -m pytest tests/ -q        # 89 tests
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
- SQLite authorizer backstop (`propops/authz.py`): the database itself
  denies writes, PRAGMA/ATTACH, and reads outside the views during
  planner queries; rows capped with `fetchmany`, never `fetchall`.
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
- Gateway hardening: a text-only SEC-SELECT-03 once let raw table names
  through (`FROM work_orders` mentioned no `v_*` to reject). Fixed with
  a base-table denylist, a SQLite authorizer backstop, and a
  fetch-time row cap — see
  [`docs/adr/0001-sqlite-authorizer-backstop.md`](docs/adr/0001-sqlite-authorizer-backstop.md)
  and `tests/test_gateway_backstop.py`.
- The triage weights (0.5/0.3/0.2) and dispatch weights (0.40/0.35/0.25)
  are reasonable defaults, not calibrated — tune against historical
  tickets before production use.
- The live parts feed is a stub; only the fake feed returns lead times.
- Synthetic data only: 30 work orders cannot prove real-world triage
  quality. The 89 checks are regression checks, not quality claims.

## Built / Written-not-run / Planned

| Item | Status |
|---|---|
| Triage engine + dispatch optimizer, gateway, RAG, signals, orchestrator, audit, PII-scrubbed feedback | Built, 89 tests green |
| Thin Streamlit demo (`demo/app.py`) | Built, logic tested via `demo_helpers` |
| `knowledge/` docs, SOPs, implementation guide, interview points, threat model | Built |
| CI workflow (`.github/workflows/ci.yml`) | Written, not run here |
| Live parts-supplier integration | Planned |
| Calibration of triage/dispatch weights on historical tickets | Planned |
| Deployment to any cloud | Planned (nothing deployed) |

## Related repos

- `Jagadish-coldchain-logistics-agents` — the FDE spine this repo follows
  (reefer telemetry; different differentiators).
- `Jagadish-retail-ops-agents` — same spine (store operations).
- `Jagadish-warehouse-ops-agents` — same spine (slotting optimizer).

---

*All data is synthetic and fictional (Harborview Property Group is an
invented name). This is an independent portfolio project, not affiliated
with any real property company.*
