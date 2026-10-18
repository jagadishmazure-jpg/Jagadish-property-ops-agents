"""ReAct orchestrator with multi-intent fan-out.

Each turn may fan out to several tools (triage, dispatch, text2sql,
sop_rag, partssignal). Every tool call is recorded in the audit log.
Safety questions (evictions, lease enforcement without confirmation)
are refused before any tool runs.
"""

from __future__ import annotations

import re
import sqlite3

from . import audit as audit_mod
from . import dispatch as dispatch_mod
from . import escalation as esc_mod
from . import partssignal as parts_mod
from . import sop_rag
from . import text2sql as t2s
from . import triage as triage_mod
from .views import install_views

_REFUSAL = re.compile(r"\b(evict|eviction|lock ?out|shut ?off (power|water))\b", re.I)


class Orchestrator:
    def __init__(self, conn: sqlite3.Connection,
                 docs_dir=None, parts_feed=None) -> None:
        self.conn = conn
        install_views(conn)
        self.audit = audit_mod.AuditLog()
        self.gate = esc_mod.ConfirmationGate()
        self.feed = parts_feed or parts_mod.FakePartsFeed()
        self.chunks = sop_rag.load_chunks(docs_dir) if docs_dir else []
        self._triage_cache: dict[str, triage_mod.TriageDecision] = {}

    def handle(self, session: str, question: str) -> dict:
        if _REFUSAL.search(question):
            self.audit.record("orchestrator", "refuse",
                              "tenant-harm action refused before any tool ran")
            return {"refused": True,
                    "reason": "I cannot take eviction or utility-shutoff "
                              "actions. A human property manager must decide."}

        result: dict = {"question": question, "tools": []}

        # fan-out 1: text-to-SQL for data questions
        try:
            data = t2s.answer(self.conn, question)
            result["tools"].append("text2sql")
            result["data"] = {"intent": data["intent"], "count": data["count"]}
            self.audit.record("orchestrator", "text2sql", data["intent"])
        except t2s.EscalationNeeded as exc:
            result["data_error"] = str(exc)

        # fan-out 2: triage a named work order
        m = re.search(r"\bWO-\d+\b", question)
        if m:
            wo = m.group(0)
            try:
                d = triage_mod.triage(self.conn, wo)
                self._triage_cache[wo] = d
                result["tools"].append("triage")
                result["triage"] = {"wo": wo, "priority": d.priority,
                                    "rules": d.rules}
                self.audit.record("orchestrator", "triage",
                                  f"{wo} -> {d.priority}")
            except ValueError as exc:
                result["triage_error"] = str(exc)

        # fan-out 3: SOP retrieval
        if self.chunks:
            hits = sop_rag.search(self.chunks, question)
            result["tools"].append("sop_rag")
            result["sops"] = [{"cite": f"{h.doc} §{h.section}",
                               "score": h.score} for h in hits]
            if not hits:
                result["sops_note"] = "no SOP found; surfacing the gap"
            self.audit.record("orchestrator", "sop_rag",
                              f"{len(hits)} hits")

        # fan-out 4: parts lead time
        m2 = re.search(r"lead time for ([\w\s-]+)", question, re.I)
        if m2:
            try:
                lt = self.feed.lead_time(m2.group(1).strip())
                result["tools"].append("partssignal")
                result["lead_time"] = {"part": lt.part, "days": lt.days,
                                       "source": lt.source}
            except parts_mod.SignalGap as exc:
                result["lead_time_gap"] = str(exc)
            self.audit.record("orchestrator", "partssignal", m2.group(1))

        result["audit_ok"] = self.audit.verify_chain()
        return result

    def dispatch_tech(self, wo_id: str) -> dict:
        """Dispatch a technician (T3-gated if P1).

        The work order is triaged first when this session has not triaged
        it, so a P1 can never skip the emergency-dispatch gate.
        """
        d = self._triage_cache.get(wo_id)
        if d is None:
            d = triage_mod.triage(self.conn, wo_id)
            self._triage_cache[wo_id] = d
        if d.priority == "P1":
            self.gate.check("emergency_dispatch")
        try:
            a = dispatch_mod.dispatch(self.conn, wo_id)
        except (dispatch_mod.NoTechAvailable, dispatch_mod.NotDispatchable) as exc:
            self.audit.record("orchestrator", "dispatch_failed", str(exc))
            return {"dispatched": False, "reason": str(exc)}
        self.audit.record("orchestrator", "dispatch",
                          f"{wo_id} -> {a.tech_id}")
        return {"dispatched": True, "tech": a.tech_id,
                "breakdown": a.breakdown}
