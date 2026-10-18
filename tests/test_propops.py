"""Regression checks for propops (synthetic data, deterministic seed 42)."""

from pathlib import Path

import pytest

from propops import audit as audit_mod
from propops import demo_helpers as dh
from propops import dispatch as dispatch_mod
from propops import escalation as esc_mod
from propops import feedback as fb_mod
from propops import orchestrator as orch_mod
from propops import partssignal as parts_mod
from propops import pii
from propops import sop_rag
from propops import telemetry
from propops import text2sql as t2s
from propops import triage as triage_mod
from propops import views
from propops.views import GatewayError

DOCS = Path(__file__).resolve().parent.parent / "docs" / "sops"


@pytest.fixture()
def conn():
    c = telemetry.seed()
    views.install_views(c)
    return c


# ---------- telemetry anchors ----------

def test_anchor_burst_pipe(conn):
    row = conn.execute(
        "SELECT urgency, residents_affected FROM work_orders "
        "WHERE wo_id='WO-1001'").fetchone()
    assert row == (5, 40)


def test_anchor_dripping_faucet(conn):
    row = conn.execute(
        "SELECT urgency FROM work_orders WHERE wo_id='WO-1002'").fetchone()
    assert row == (1,)


def test_anchor_gas_odor(conn):
    row = conn.execute(
        "SELECT category FROM work_orders WHERE wo_id='WO-1007'").fetchone()
    assert row == ("safety",)


def test_anchor_tech001(conn):
    row = conn.execute(
        "SELECT skills, home_building, shift FROM technicians "
        "WHERE tech_id='TECH-001'").fetchone()
    assert row == ("plumbing,hvac", "BLDG-01", "day")


def test_anchor_overdue_preventive(conn):
    row = conn.execute(
        "SELECT status FROM preventive WHERE task_id='PM-201'").fetchone()
    assert row == ("overdue",)


def test_anchor_repeat_unit(conn):
    n = conn.execute(
        "SELECT COUNT(*) FROM work_orders WHERE unit_id='BLDG-01-U014' "
        "AND category='plumbing'").fetchone()[0]
    assert n >= 3


# ---------- gateway security ----------

def test_gateway_rejects_non_select(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "DELETE FROM v_open_wos")
    assert e.value.rule_id == "SEC-SELECT-01"


def test_gateway_rejects_stacked(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "SELECT * FROM v_open_wos; SELECT 1")
    assert e.value.rule_id == "SEC-SELECT-02"


def test_gateway_rejects_write_keyword(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "SELECT * FROM v_open_wos WHERE 1=1 UPDATE x")
    assert e.value.rule_id == "SEC-SELECT-02"


def test_gateway_allows_write_word_inside_literal(conn):
    rows = views.run_query(
        conn, "SELECT wo_id FROM v_open_wos WHERE summary = 'drop table'")
    assert isinstance(rows, list)  # stripped literal -> no false positive


def test_gateway_rejects_unknown_view(conn):
    with pytest.raises(GatewayError) as e:
        views.run_query(conn, "SELECT * FROM v_nonexistent")
    assert e.value.rule_id == "SEC-SELECT-03"


def test_gateway_allows_valid_query(conn):
    rows = views.run_query(conn, "SELECT wo_id FROM v_open_wos")
    assert len(rows) > 0 and "wo_id" in rows[0]


def test_gateway_caps_rows_at_fetch_time(conn):
    rows = views.run_query(conn, "SELECT wo_id FROM v_open_wos", limit=5)
    assert len(rows) <= 5


def test_gateway_comment_rejected(conn):
    with pytest.raises(GatewayError):
        views.run_query(conn, "SELECT * FROM v_open_wos -- sneaky")


# ---------- text2sql ----------

def test_intent_open_wos(conn):
    out = t2s.answer(conn, "Which open work orders are P1?")
    assert out["intent"] == "open_wos_by_priority" and out["count"] > 0


def test_intent_tech_utilization(conn):
    out = t2s.answer(conn, "Which technicians are available right now?")
    assert out["intent"] == "tech_utilization"


def test_intent_overdue_preventive(conn):
    out = t2s.answer(conn, "Show me overdue preventive maintenance tasks")
    assert out["intent"] == "overdue_preventive"
    assert any(r["task_id"] == "PM-201" for r in out["rows"])


def test_intent_repeat_issues(conn):
    out = t2s.answer(conn, "Are there repeat issues in the same unit again?")
    assert out["intent"] == "repeat_issues"


def test_intent_satisfaction(conn):
    out = t2s.answer(conn, "What are the tenant satisfaction trends?")
    assert out["intent"] == "satisfaction_trends"


def test_no_intent_escalates(conn):
    with pytest.raises(t2s.EscalationNeeded):
        t2s.answer(conn, "What is the meaning of life?")


# ---------- triage differentiator ----------

def test_triage_burst_pipe_p1(conn):
    d = triage_mod.triage(conn, "WO-1001")
    assert d.priority == "P1"
    assert any("TR-P1-01" in r for r in d.rules)


def test_triage_gas_odor_safety_p1(conn):
    d = triage_mod.triage(conn, "WO-1007")
    assert d.priority == "P1"
    assert any("TR-P1-02" in r for r in d.rules)


def test_triage_faucet_p4(conn):
    d = triage_mod.triage(conn, "WO-1002")
    assert d.priority == "P4"
    assert any("TR-P4-01" in r for r in d.rules)


def test_triage_repeat_bump(conn):
    d = triage_mod.triage(conn, "WO-1012")  # urgency 3 -> P3 base
    assert d.priority == "P2"              # bumped one level
    assert any("TR-ESC-01" in r for r in d.rules)


def test_triage_score_formula(conn):
    d = triage_mod.triage(conn, "WO-1001")
    assert d.score == 4.8
    assert "0.5*5(urgency)" in d.breakdown


def test_triage_cites_rule(conn):
    d = triage_mod.triage(conn, "WO-1002")
    assert len(d.rules) >= 1 and all("TR-" in r for r in d.rules)


def test_triage_unknown_wo(conn):
    with pytest.raises(ValueError):
        triage_mod.triage(conn, "WO-9999")


def test_triage_persists_priority(conn):
    triage_mod.triage(conn, "WO-1001")
    row = conn.execute(
        "SELECT priority FROM work_orders WHERE wo_id='WO-1001'").fetchone()
    assert row == ("P1",)


# ---------- dispatch differentiator ----------

def test_dispatch_picks_qualified_tech(conn):
    a = dispatch_mod.dispatch(conn, "WO-1001")  # plumbing, BLDG-01
    assert a.tech_id == "TECH-001"


def test_dispatch_breakdown_format(conn):
    a = dispatch_mod.dispatch(conn, "WO-1001")
    assert "skill" in a.breakdown and "proximity" in a.breakdown


def test_dispatch_excludes_off_shift(conn):
    conn.execute("UPDATE technicians SET shift='off' "
                 "WHERE tech_id IN ('TECH-001','TECH-003')")
    conn.commit()
    with pytest.raises(dispatch_mod.NoTechAvailable):
        dispatch_mod.dispatch(conn, "WO-1001")  # no plumbing tech on shift


def test_dispatch_never_guesses(conn):
    conn.execute("UPDATE technicians SET shift='off'")
    conn.commit()
    with pytest.raises(dispatch_mod.NoTechAvailable):
        dispatch_mod.dispatch(conn, "WO-1002")


def test_dispatch_increments_load(conn):
    before = conn.execute(
        "SELECT active_wos FROM technicians WHERE tech_id='TECH-001'"
    ).fetchone()[0]
    dispatch_mod.dispatch(conn, "WO-1001")
    after = conn.execute(
        "SELECT active_wos FROM technicians WHERE tech_id='TECH-001'"
    ).fetchone()[0]
    assert after == before + 1


def test_dispatch_marks_assigned(conn):
    dispatch_mod.dispatch(conn, "WO-1001")
    row = conn.execute(
        "SELECT status FROM work_orders WHERE wo_id='WO-1001'").fetchone()
    assert row == ("assigned",)


def test_dispatch_unknown_wo(conn):
    with pytest.raises(ValueError):
        dispatch_mod.dispatch(conn, "WO-9999")


# ---------- parts signal ----------

def test_fake_feed_deterministic():
    f1, f2 = parts_mod.FakePartsFeed(), parts_mod.FakePartsFeed()
    assert f1.lead_time("boiler pressure valve").days == \
        f2.lead_time("boiler pressure valve").days


def test_fake_feed_unknown_part():
    lt = parts_mod.FakePartsFeed().lead_time("flux capacitor")
    assert lt.days >= 1 and lt.source == "fake"


def test_live_feed_gap():
    with pytest.raises(parts_mod.SignalGap):
        parts_mod.LivePartsFeed().lead_time("boiler pressure valve")


# ---------- SOP RAG ----------

def test_rag_finds_triage_sop():
    chunks = sop_rag.load_chunks(DOCS)
    hits = sop_rag.search(chunks, "triage priority rules severity")
    assert hits and hits[0].doc == "sop-01-triage-playbook.md"


def test_rag_citation_format():
    chunks = sop_rag.load_chunks(DOCS)
    hits = sop_rag.search(chunks, "technician dispatch skill ranking")
    assert hits
    cite = f"{hits[0].doc} §{hits[0].section}"
    assert "§" in cite


def test_rag_explicit_not_found():
    chunks = sop_rag.load_chunks(DOCS)
    assert sop_rag.search(chunks, "quantum cryptography policy") == []


def test_rag_skips_title_only_chunks():
    chunks = sop_rag.load_chunks(DOCS)
    assert all(not c.text.startswith("#") for c in chunks)


# ---------- escalation ----------

def test_tiers_defined():
    assert set(esc_mod.TIERS) == {"T1", "T2", "T3", "T4"}


def test_tier_for_p1():
    assert esc_mod.tier_for("P1") == "T2"


def test_tier_for_repeat():
    assert esc_mod.tier_for("P3", repeat=True) == "T2"


def test_gate_denies_by_default():
    with pytest.raises(esc_mod.GateDenied):
        esc_mod.ConfirmationGate().check("emergency_dispatch")


def test_gate_allows_with_approver():
    esc_mod.ConfirmationGate(approver=lambda a: True).check(
        "emergency_dispatch")  # no raise


def test_lease_enforcement_gated():
    assert "lease_violation_enforcement" in esc_mod.GATED_ACTIONS


# ---------- audit ----------

def test_audit_chain_verifies():
    log = audit_mod.AuditLog()
    log.record("dispatcher", "triage", "WO-1001 -> P1")
    log.record("dispatcher", "dispatch", "WO-1001 -> TECH-001")
    assert log.verify_chain()


def test_audit_tamper_breaks_chain():
    log = audit_mod.AuditLog()
    log.record("dispatcher", "triage", "WO-1001 -> P1")
    log.entries[0].details = "WO-1001 -> P4"
    assert not log.verify_chain()


def test_audit_truncates_details():
    log = audit_mod.AuditLog()
    e = log.record("x", "y", "z" * 1000)
    assert len(e.details) <= 500


# ---------- PII scrubbing ----------

def test_scrub_email():
    clean, n = pii.scrub("tenant jane@example.com reported a leak")
    assert "[EMAIL]" in clean and n == 1


def test_scrub_phone():
    clean, n = pii.scrub("call me at 555-123-4567")
    assert "[PHONE]" in clean and n == 1


def test_scrub_ssn():
    clean, n = pii.scrub("ssn 123-45-6789 on file")
    assert "[SSN]" in clean and n == 1


def test_scrub_clean_text_untouched():
    clean, n = pii.scrub("the faucet drips every night")
    assert clean == "the faucet drips every night" and n == 0


# ---------- feedback ----------

def test_feedback_stores_scrubbed(tmp_path):
    store = fb_mod.FeedbackStore(tmp_path / "fb.jsonl")
    fb = store.add("s1", 0, "correction",
                   "wrong, email me at bob@example.com", wo_id="WO-1001")
    assert "[EMAIL]" in fb.text and fb.redactions == 1
    assert "bob@example.com" not in (tmp_path / "fb.jsonl").read_text()


def test_feedback_rejects_bad_kind(tmp_path):
    store = fb_mod.FeedbackStore(tmp_path / "fb.jsonl")
    with pytest.raises(fb_mod.FeedbackError):
        store.add("s1", 0, "hug", "nice")


def test_feedback_rejects_bad_session(tmp_path):
    store = fb_mod.FeedbackStore(tmp_path / "fb.jsonl")
    with pytest.raises(fb_mod.FeedbackError):
        store.add("", -1, "thumbs_up", "ok")


def test_feedback_roundtrip(tmp_path):
    store = fb_mod.FeedbackStore(tmp_path / "fb.jsonl")
    store.add("s2", 3, "thumbs_up", "fixed fast")
    assert len(store.all()) == 1


# ---------- orchestrator ----------

def test_orchestrator_refuses_eviction(conn):
    orch = orch_mod.Orchestrator(conn)
    out = orch.handle("s1", "evict the tenant in BLDG-01-U014")
    assert out["refused"] is True


def test_orchestrator_fans_out(conn):
    orch = orch_mod.Orchestrator(conn, docs_dir=DOCS)
    out = orch.handle("s1", "triage WO-1001")
    assert "triage" in out["tools"]
    assert out["triage"]["priority"] == "P1"


def test_orchestrator_audit_ok(conn):
    orch = orch_mod.Orchestrator(conn, docs_dir=DOCS)
    out = orch.handle("s1", "Which open work orders are P1?")
    assert out["audit_ok"] is True


def test_orchestrator_p1_dispatch_gated(conn):
    orch = orch_mod.Orchestrator(conn)
    orch.handle("s1", "triage WO-1001")
    with pytest.raises(esc_mod.GateDenied):
        orch.dispatch_tech("WO-1001")


def test_orchestrator_parts_gap(conn):
    orch = orch_mod.Orchestrator(conn, parts_feed=parts_mod.LivePartsFeed())
    out = orch.handle("s1", "what is the lead time for boiler pressure valve")
    assert "lead_time_gap" in out


def test_orchestrator_sop_gap_noted(conn):
    orch = orch_mod.Orchestrator(conn, docs_dir=DOCS)
    out = orch.handle("s1", "quantum cryptography policy")
    assert out.get("sops_note") == "no SOP found; surfacing the gap"


# ---------- demo helpers ----------

def test_demo_triage(conn):
    out = dh.triage_work_order(conn, "WO-1002")
    assert out["priority"] == "P4"


def test_demo_dispatch(conn):
    out = dh.dispatch_for(conn, "WO-1002")
    assert out["dispatched"] is True and out["tech_id"] in {
        "TECH-001", "TECH-003"}


def test_demo_ask_escalates(conn):
    out = dh.ask(conn, "meaning of life")
    assert out.get("escalated") is True


def test_demo_open_wo_summary(conn):
    out = dh.open_wo_summary(conn)
    assert isinstance(out, list)
