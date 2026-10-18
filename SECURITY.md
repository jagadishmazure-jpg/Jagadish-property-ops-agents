# Security policy

## Reporting a vulnerability

This is a synthetic-data demo project. If you find a security issue, please
open a GitHub issue describing it — do not include any real tenant, property,
or personal data.

## Built-in controls

- The text-to-SQL layer is a SELECT-only gateway: single SELECT statements,
  no stacked queries, no comments, no DDL/DML keywords outside string
  literals, and only the four published read-only views are reachable.
  Violations raise `GatewayError` with a cited rule ID
  (SEC-SELECT-01/02/03).
- Free-text feedback is PII-scrubbed (email, phone, SSN, card patterns)
  **before** it is written to storage.
- Emergency dispatch and lease-violation enforcement require a human
  confirmation gate; the gate denies on timeout.
- The audit log is hash-chained; tampering breaks `verify_chain()`.
