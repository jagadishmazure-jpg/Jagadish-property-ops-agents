# Interview points

- **Why two differentiators?** Triage and dispatch are separate decisions
  with separate failure modes. Triage fails by under-prioritizing safety;
  dispatch fails by sending the wrong skill. One module per decision keeps
  the rules citable and the tests isolated.
- **Why is skill a hard filter, not a weight?** An unqualified repair
  creates a second ticket and a safety risk. Weights rank; filters
  protect. The optimizer raises `NoTechAvailable` instead of guessing —
  a deliberate choice to fail loudly.
- **How do you know the gateway is safe?** Three cited rules, tested both
  ways: valid queries pass, and each attack class (stacked statements,
  comments, DDL/DML keywords, unknown views) has a regression check,
  including the literal-stripping false-positive case.
- **What happens when the live parts feed is down?** `SignalGap`, surfaced
  verbatim. The agent never quotes a lead time it did not retrieve.
- **Where does the human sit?** Emergency dispatch and lease-violation
  enforcement wait on the confirmation gate (denies on timeout). Eviction
  and utility-shutoff requests are refused before any tool runs.
- **How is feedback kept safe?** PII scrubbing runs before storage, not
  after — the exact gap a review caught in sibling repos, built in here
  from the start. Redaction counts are kept for the audit trail.
