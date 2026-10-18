"""Thin Streamlit demo — all logic lives in propops.demo_helpers (tested).

Run:  pip install streamlit && streamlit run demo/app.py
"""

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    raise SystemExit("pip install streamlit, then re-run") from None

from propops import demo_helpers as dh

st.title("Pellcrest Property Ops — agent demo")
st.caption("Synthetic data. All numbers below come from the local SQLite seed.")

conn = dh.get_conn()

q = st.text_input("Ask about work orders",
                  "Which open work orders are P1?")
if st.button("Ask"):
    st.json(dh.ask(conn, q))

wo = st.text_input("Triage a work order", "WO-1001")
if st.button("Triage + dispatch"):
    t = dh.triage_work_order(conn, wo)
    st.json(t)
    if t["priority"] == "P1":
        st.warning("P1 dispatch needs human confirmation (gate).")
    else:
        st.json(dh.dispatch_for(conn, wo))

st.subheader("Open work orders by priority")
st.json(dh.open_wo_summary(conn))
