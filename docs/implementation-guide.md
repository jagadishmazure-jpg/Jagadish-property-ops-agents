# Implementation guide

## Run it
```bash
python -m pytest tests/ -q        # 69 regression checks, stdlib only
python scripts/count_tests.py     # prints the real total
```
Optional demo UI:
```bash
pip install streamlit
streamlit run demo/app.py
```
All demo logic lives in `propops/demo_helpers.py` and is covered by tests;
`demo/app.py` only renders.

## How the pieces fit
- `telemetry.py` — `seed()` builds the synthetic SQLite database
  (deterministic, seed 42). Anchor records are documented in the module
  docstring; tests pin them.
- `views.py` — four read-only views plus the SELECT-only gateway. To add a
  view, add it to `VIEWS`; the gateway picks it up automatically and the
  SEC-SELECT-03 check keeps queries inside the published set.
- `text2sql.py` — fixed intent patterns and templates. To add an intent,
  append a `(name, pattern, template)` tuple to `_INTENTS` and add a test.
  One simplified repair retry, then `EscalationNeeded`.
- `triage.py` — the triage engine. Rule IDs (`TR-P1-01` … `TR-ESC-01`)
  are cited in every decision; keep them stable because the audit log and
  README reference them.
- `dispatch.py` — the dispatch optimizer. Skill is a hard filter; the
  weights (0.40/0.35/0.25) are in one place at the top of `dispatch()`.
- `orchestrator.py` — fan-out across tools with per-call audit records.
  The refusal regex (`_REFUSAL`) runs before any tool.

## Adapting to a real portfolio
Replace `telemetry.seed()` with a read-only connector to the real
work-order system, keep the gateway in front of it, and keep the
confirmation gate on emergency dispatch. The triage weights and rule IDs
are the tuning surface — calibrate them against historical tickets
before trusting the scores.
