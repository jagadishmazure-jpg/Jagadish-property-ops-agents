# Technician dispatch

## Skill is a hard filter
Never assign a technician who lacks the required skill, even if they are the only one nearby. An unqualified repair creates a second ticket and a safety risk.

## Ranking
Among qualified technicians on an active shift, rank by skill depth, proximity to the building, and current load. The optimizer publishes a per-factor breakdown with every assignment so the dispatcher can see why a tech was picked.

## Off-shift and overload
Technicians marked off are never assigned. A technician at maximum load is never assigned — the optimizer raises a no-availability signal instead of guessing, and the dispatcher escalates to the supervisor for contractor coverage.

## Emergency dispatch
P1 dispatches are emergency dispatches and require human confirmation through the confirmation gate before the technician is notified.
