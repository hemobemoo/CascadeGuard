# Spec 002 — Engine with scripted agents, and diagnosis

## Goal

Run `uae_health_access` end to end with `ScriptedAgent`s and no API key. The engine decides
every action, and diagnosis names the coordination failure. The run must be deterministic, and
no agent may see data outside its boundary.

## Flow (`simulation/orchestrator.py`, deterministic code, not an agent)

For each inject in time order:
1. `ConstraintEngine.release(event)`. Deadlines that passed are marked missed. The state moves
   to the inject's minute. The inject's facts go to their holder and to recipients whose
   boundary includes the category. `opens_obligations` clauses open obligations; a clause that
   is not loaded becomes a `trigger_not_loaded` finding.
2. Every role gets a frozen `RoleView` (`simulation/boundaries.py`): tuples and frozen models,
   only facts inside its boundary, the loaded clauses relevant to the inject with their status
   labels, and its own accepted actions. Views are built before any decision is applied.
3. Each agent returns an `AgentDecision`. The engine processes them in `roles.yaml` order.

Then the engine closes the run, `engine/graph.py` builds the dependency graph, and
`engine/diagnosis.py` explains every unmet critical recovery goal.

## Engine rules (`engine/constraints.py`)

- **Decision level.** The role and time must match. A citation of a clause the engine did not
  load rejects the whole decision: `draft_citation` if the clause exists as a draft, otherwise
  `unknown_citation`. Both are recorded as findings.
- **Action level.** The action must be in the role's allowed set. `share_incident_status` needs
  a fact the sender knows. It is rejected if the category is outside the recipient's boundary
  (`outside_recipient_boundary`), or if a loaded prohibition or data safeguard covers that
  category (`restricted_by_clause`). `roles.yaml` preconditions are checked:
  `requires_prior`, `requires_information`, and `requires_authority`.
- **Authority.** An obligation or permission clause naming the role (or `any`) counts if it is
  binding, or if it is an illustrative scenario rule (`binding: false`). A clause with
  `binding: unknown` gives only `authority_uncertain`. Non-binding guidance never counts.
  `stated` and `interpreted` readings are treated the same.
- Accepted effects: shares deliver the fact (boundary checked again), obligations with the same
  role and action are fulfilled, and goals are met. Every step is appended to the log.

## Diagnosis (`engine/diagnosis.py`)

| Category | Raised when |
|---|---|
| Information deadlock | A role needs a category (a knowledge goal, or an action's `requires_information`) that another role holds but that is outside its boundary or was never shared |
| Orphan duty | A goal action needs authority and no candidate role has it (an uncertain candidate is named) |
| Undefined trigger | A prerequisite action of a goal action is obliged by no loaded clause |
| Temporal infeasibility | An obligation's deadline passed unfulfilled |
| Mandate overlap | **Not detected yet.** It needs reviewed DHA/PDPL clauses to compare; deferred |

Every failure carries a qualification: "not found in the loaded clause set (...)". It is never
a confirmed legal gap. Undetermined deadlines are findings, not failures.

## Clause sets

- `cascadeguard run uae_health_access` uses `policies/reviewed` (reviewed and illustrative).
  Today that is the two illustrative telecom rules, so most scripted decisions are rejected for
  draft citations. The output says so.
- `--clauses tests/fixtures/clauses` uses synthetic illustrative fixtures that mirror the draft
  clauses' `normalized` readings and binding status, under the same ids. They are labelled
  "SYNTHETIC FIXTURES ... not the real corpus" everywhere. They are for tests only.

## Done when

- `tests/integration/test_baseline.py` reproduces
  `tests/fixtures/uae_health_access/expected_baseline.yaml` exactly, twice, with the same
  result.
- `tests/unit/test_boundaries.py` shows that no role ever sees a fact outside its boundary, and
  that views hold no state and no mutable containers.

The real-corpus golden `scenarios/uae_health_access/expected_baseline.yaml` is added after the
human reviews the core clause set (gate 1).
