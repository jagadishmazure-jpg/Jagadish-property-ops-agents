# Threat model (STRIDE-lite)

## Spoofing
- The demo has no authentication; in a real deployment the dispatcher
  identity must come from the property-management SSO, not the prompt.

## Tampering
- The audit log is hash-chained; `verify_chain()` detects edits.
- The SQLite seed is synthetic and in-memory; a real deployment needs a
  read-only service account (the gateway is SELECT-only by construction).

## Repudiation
- Every tool call is audit-logged with actor, action, and a 500-char
  detail cap. Confirmation-gate decisions are logged with the outcome.

## Information disclosure
- The gateway exposes only four views — no tenant names, no unit-level
  PII beyond what the views publish. Feedback text is PII-scrubbed
  before storage.
- Error messages never echo raw row data.

## Denial of service
- 100-row cap on gateway queries; TF-IDF runs over four small SOP files.

## Elevation of privilege
- text-to-SQL cannot reach DDL/DML (SEC-SELECT-02, tested). The
  orchestrator cannot send tenant messages or take enforcement actions —
  refusal regex plus confirmation gate.

## LLM-specific (OWASP LLM Top 10, where relevant)
- **Prompt injection:** tenant-authored work-order summaries flow into the
  triage engine as data, never as instructions; the fixed-intent
  text-to-SQL has no free-form generation to hijack.
- **Excessive agency:** the agent drafts but never sends; gated actions
  need a human.
