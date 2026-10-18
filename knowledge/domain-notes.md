# Domain notes — property maintenance operations

Distilled from the four SOPs in `docs/sops/` (written for this repo, own
words). All entities below are fictional.

## The job
A property operations team keeps buildings habitable: intake maintenance
requests, triage them by urgency and impact, dispatch qualified
technicians, run preventive maintenance on schedule, and keep tenants
informed. The failure mode that matters most is a slow or wrong response
to a safety issue — gas, flooding, sparking electrical.

## Key concepts
- **Work order (WO):** a tenant-reported or staff-reported maintenance
  request with a category (plumbing, electrical, HVAC, appliance,
  structural, pest, safety), an urgency 1–5, and a resident count.
- **Triage:** scoring urgency × tenant impact × asset criticality into
  P1–P4. Safety categories bypass scoring entirely (auto-P1).
- **Repeat issue:** the same category in the same unit 3+ times in 30
  days. Almost always a line/system problem, not a tenant problem —
  bump priority and open a root-cause note.
- **Dispatch:** skill is a hard filter; rank the qualified on-shift techs
  by skill depth, proximity, and current load. Never guess — raise
  no-availability and escalate for contractor coverage.
- **Preventive maintenance:** due dates are commitments. Overdue elevator,
  boiler, and fire-alarm tasks escalate the same day.
- **Tenant communication:** acknowledge fast, use plain language, survey
  after close, and never let the agent send enforcement-adjacent messages
  without a human.

## Numbers that shape the design
- P1 SLA is 15 minutes to acknowledge; that is why safety auto-P1 skips
  the scoring path entirely.
- A technician at 5 active work orders is fully loaded — the optimizer
  stops assigning rather than queueing silently.
- Satisfaction scores below 3 trigger a supervisor callback within
  48 hours; the trend view exists so managers see buildings, not tickets.
