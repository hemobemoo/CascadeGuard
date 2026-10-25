# ADR 0002 — How repairs reach LLM agents

Status: **decided (human, 2026-10-26)**. Option A is not implemented yet.

**Decision:** Phase 5 closes with C. A is the first task after Phase 5, pending the human's
decision on when the owner obligation opens and its deadline. B is not taken.

## Context

In the paced live replay of the golden repair (owner + share, 2026-10-25), the health operator
received the network status but never proposed `reverse_automated_lockouts`. Its T+45 reasoning
listed "who owns reviewing and reversing automated lockouts within my remit" as unknown,
although the repair rule naming it the owner was in its view. Result: LLM **partial**, scripted
**resolved**.

What the engine does today (checked in code and on the golden replay):

- `assign_owner` becomes a hypothetical rule `repair.<edit>` of kind *obligation*. That gives
  the owner **authority** (`RuleBook.authority`), but **no obligation is opened**. The engine
  opens obligations only for clauses an inject lists in `opens_obligations`
  (`ConstraintEngine.release`), and owner edits carry no trigger event. The golden replay's
  obligations are the same three as the baseline's.
- `RoleView` lists no obligations (open or otherwise). Repair rules appear in the prompt only
  under `repair_rules_not_citable` (P5-5).

## Options

### A. The owner repair opens an obligation; views list open obligations

The engine opens an obligation for the new owner when the owner repair applies, and `view_for`
adds the role's open obligations (action, clause/rule id with label, due or "undetermined").

- **AGENTS.md rules:** none changed. Obligations stay engine state; agents still only propose.
  Needs a design decision on **when** the obligation opens and its **deadline** (proposal: at
  the inject that first reveals the orphan duty's goal, deadline "undetermined"). An unfulfilled
  owner obligation would become a new conflict (temporal infeasibility). For scripted agents
  that is the existing `scripted_agent_limit` tag (decision 4e), so ranking is affected.
- **Caches invalidated:** every LLM decision (v2 and v3), because every view changes (open
  obligations appear from T+00: raise_security_incident, notify_health_data_oversight,
  report_to_telecom_regulator). Scripted goldens: `expected_repairs.yaml` likely changes
  (owner repairs gain an obligation and its finding); `expected_baseline.yaml` only if the
  obligations list format changes (views are not in the golden).
- **Requests (estimate):** new baseline 36 steps plus replay of about 25 to 36 changed steps,
  so 61 to 72 asked steps. With the observed overhead (v3 baseline 37 requests for 36 steps;
  paced replay 27 for 22), about **70 to 90 requests**. Cost 0 on the current free model.

### B. Repair rules in force and citable by repair id

Show active repair rules as rules in force for this replay, citable as `repair.<edit>`, still
labelled "hypothetical repair rule (not a source clause)".

- **AGENTS.md rules:** **changes** "Every Citation must reference a clause ID that exists in
  `policies/reviewed/`", which is human gate 6. Engine: accept `repair.*` citations only in a
  replay that loaded them, never in a baseline, and keep them out of anything presented as law.
  Risk: blurs the line between source law and simulation rules in citations and exports.
- **Caches invalidated:** the prompt changes only for views that contain repair rules. If the
  prompt version is bumped only for those prompts, the v3 baseline cache stays valid;
  otherwise all LLM decisions are invalidated.
- **Requests (estimate):** replay only, about 25 changed steps, so **about 28 to 32
  requests** (baseline reused). With a global prompt bump: about **70 to 90**, as in A.
- It does not tell the agent it *must* act; it only lets it cite the rule. The failure seen
  was about ownership, not citation.

### C. Keep as is; report the partial result as a finding

- **AGENTS.md rules:** none changed. **Caches:** none invalidated. **Requests:** 0.
- The limitation is stated: LLM replays understate repairs that only work if an agent takes up
  a new duty (the LLM analogue of `scripted_agent_limit`).

## Recommendation

**C now, A next.** Close Phase 5 with C (already recorded in `docs/review/phase-5-report.md` and
PROGRESS). Then do A as the first item after Phase 5, because:

- it stays inside the AGENTS.md boundary: the deterministic engine opens and enforces
  obligations, and agents only see them;
- it also answers the deferred open-obligations question (notify_health_data_oversight was
  missed in the v2 LLM baseline for the same reason);
- it gives scripted and LLM agents the same, checkable signal.

B is not recommended: it changes a core evidence rule to fix what is an obligation problem, not
a citation problem.

Before A: the human decides when an owner obligation opens and its deadline, and approves
regenerating the affected goldens and one capped LLM baseline plus replay.
