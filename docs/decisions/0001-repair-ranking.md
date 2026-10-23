# ADR 0001 — Repair ranking: clean repairs first, blockers counted by cause

Date: 2026-10-24. Status: accepted (human decisions 4a, 4b, 4e).

## Context

`START_PROMPT.md` and the first `AGENTS.md` text ranked repairs by: hard filter, most critical
blockers removed, fewest edits, then tie-breaks (no authorization needed, fewest roles and
clauses, `repair_id`). Phase 3 review found two problems with that order:

- A blocker counted as "removed" when the replay no longer diagnosed it, even if it was only
  hidden because its goal was met another way (4a).
- A repair that introduced a new conflict could outrank a clean partial repair by removing more
  blockers (4e), although `CascadeGuard.md` §6 calls such a repair "failed".

`CascadeGuard.md` §6 is authoritative: preserve safeguards first, remove real blockers second,
minimise edits third.

## Decision

1. Hard filters, unchanged.
2. Clean repairs (no new conflict) rank above any repair that introduces a new conflict.
3. Within each group: most critical blockers removed, fewest edits, fewest roles touched, fewest
   clauses cited.
4. Among repairs with new conflicts: fewest new conflicts.
5. Then not requiring authorization, then `repair_id` (the human's order does not place the
   authorization tie-break; it is kept last so it never overrides steps 2-4).

A blocker is removed only when the repair removes its cause (the replay, diagnosed with met
goals examined too, no longer finds it). Otherwise it is "masked (goal met another way)".
Repairs with new conflicts are ranked lower, not discarded; a conflict that is only a duty the
scripted agents never attempt is tagged `scripted_agent_limit` for Phase 5.

## Consequences

- Fewer blockers count as removed: the two "resolved" repairs drop from 4 to 2 removed, with 2
  masked. Six two-edit repairs now tie on blockers and edits; roles touched decides, so
  owner + trigger (one role, partial) ranks above owner + share (two roles, resolved). Whether
  a resolved repair should outrank a partial one is not part of this order; it would need a
  new key.
- All repairs with new conflicts (the decision-requester repairs) now rank below every clean
  repair.
- `scenarios/uae_health_access/expected_repairs.yaml` was regenerated; the PR shows old and new
  ranks side by side.
