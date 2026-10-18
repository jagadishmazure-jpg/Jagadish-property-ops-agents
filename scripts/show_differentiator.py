"""Print the triage engine, dispatch optimizer and gateway on the seeded data."""
from propops import demo_helpers as dh
from propops import dispatch as dispatch_mod
from propops import escalation as esc_mod
from propops import orchestrator as orch_mod
from propops import triage as triage_mod
from propops import views

conn = dh.get_conn()
print("Triage (priority = higher of rule ladder and score band; repeat bump last):")
for wo in ("WO-1001", "WO-1007", "WO-1010", "WO-1011", "WO-1012", "WO-1016", "WO-1032"):
    d = triage_mod.triage(conn, wo)
    print(f"  {wo} -> {d.priority} {d.score} | {'; '.join(r.split(' (')[0] for r in d.rules)}")

print("Dispatch (skill hard filter, open work orders only, max load respected):")
for wo in ("WO-1001", "WO-1018", "WO-1029", "WO-1007", "WO-1016"):
    try:
        a = dispatch_mod.dispatch(conn, wo)
        print(f"  {wo} -> {a.tech_id} | {a.breakdown}")
    except (dispatch_mod.NoTechAvailable, dispatch_mod.NotDispatchable) as exc:
        print(f"  {wo} -> not dispatched: {exc}")

o = orch_mod.Orchestrator(dh.get_conn())
try:
    o.dispatch_tech("WO-1001")
except esc_mod.GateDenied as exc:
    print(f"Emergency dispatch of untriaged P1 WO-1001: {exc}")

for sql in ("SELECT * FROM v_open_wos, work_orders",):
    try:
        views.run_query(conn, sql)
    except views.GatewayError as exc:
        print(f"Gateway: {sql} -> {exc}")
