# ADR 0001 — Repair ranking: clean, then resolved, then blockers counted by cause

Date: 2026-10-24. Status: accepted (human decisions 4a, 4b, 4e, and the follow-up the same day).

## Context

`START_PROMPT.md` and the first `AGENTS.md` text ranked repairs by: hard filter, most critical
blockers removed, fewest edits, then tie-breaks (no authorization needed, fewest roles and
clauses, `repair_id`). Phase 3 review found three problems with that order:

- A blocker counted as "removed" when the replay no longer diagnosed it, even if it was only
  hidden because its goal was met another way (4a).
- A repair that introduced a new conflict could outrank a clean partial repair by removing more
  blockers (4e), although `CascadeGuard.md` §6 calls such a repair "failed".
- Once blockers were counted by cause (first version of this ADR), a partial repair touching
  fewer roles outranked the repairs that meet every critical goal.

`CascadeGuard.md` §6 is authoritative: preserve safeguards first, remove real blockers second,
minimise edits third.

## Decision

1. Hard filters, unchanged.
2. Clean repairs (no new conflict) above repairs with a new conflict.
3. Resolved (every critical goal met in the replay) above partial, then most critical goals met.
4. Most critical blockers removed at their cause.
5. Fewest critical blockers only masked.
6. Fewest edits. 7. Fewest roles touched. 8. Fewest clauses cited.
9. Not requiring authorization. 10. `repair_id`.

Among repairs with a new conflict, fewest new conflicts breaks the ties left after step 8.

A blocker is removed only when the repair removes its cause (the replay, diagnosed with met
goals examined too, no longer finds it). Otherwise it is "masked (goal met another way)".
Repairs with new conflicts are ranked lower, not discarded; a conflict that is only a duty the
scripted agents never attempt is tagged `scripted_agent_limit` for Phase 5.

**Why "resolved" outranks "blockers removed":** the concept's aim is a feasible recovery path
for the incident, so a repair that meets every critical goal answers the question better than
one that removes more causes but leaves patients locked out. Nothing is hidden by this: masked
blockers stay visible as findings in every output, and step 5 still prefers the resolved repair
that leaves fewer of them.

## Consequences

- Owner + share and fallback + share (both resolved, 2 removed, 2 masked) rank first and
  second; partial repairs follow, ordered by critical goals met, then blockers removed.
- All repairs with new conflicts (the decision-requester repairs) rank below every clean repair.
- `scenarios/uae_health_access/expected_repairs.yaml` was regenerated with each change.
