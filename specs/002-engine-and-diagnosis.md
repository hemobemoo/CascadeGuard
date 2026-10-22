# Spec 002 — Engine with scripted agents, and diagnosis

## Goal

Run `uae_health_access` end to end with `ScriptedAgent`s and no API key. The engine decides
every action, and diagnosis names the coordination failure. The run must be deterministic, and
no agent may see data outside its boundary.

## Flow (`simulation/orchestrator.py`, deterministic code, not an agent)

For each inject in time order:
1. `ConstraintEngine.release(event)`. Deadlines that passed are marked missed. The state moves
   to the inject's minute. The inject's facts go to their holder and to recipients whose
   boundary includes the category. `opens_obligations` clauses open obligations: a clause that
   is not loaded is a `trigger_not_loaded` finding, a non-obligation clause is a
   `trigger_not_obligation` finding, and a `binding: unknown` clause opens an obligation marked
   uncertain (its missed deadline is reported with the "uncertain" qualification).
2. Every role gets a frozen `RoleView` (`simulation/boundaries.py`). It holds tuples and deep
   copies of facts inside the role's boundary, and the role's own accepted actions. Recipients of
   the inject also get its title and description (which hold only what all recipients may know)
   and its relevant loaded clauses with status labels; each decision point goes only to the role
   it names. Everyone else gets only "no new inject". Views are built before any decision is applied.
3. Each agent returns an `AgentDecision`. The engine processes them in `roles.yaml` order.

Then the engine closes the run, `engine/graph.py` builds the dependency graph, and
`engine/diagnosis.py` explains every unmet critical recovery goal.

## Engine rules (`engine/constraints.py`)

- **Untrusted agents.** Whatever an agent returns is re-validated from plain data
  (`model_dump` then `model_validate`); anything that is not a valid `AgentDecision` is a
  `malformed_decision` finding. The fact a share delivers is read once, checked, and delivered
  as checked. The state never releases a fact before its inject.
- **Decision level.** Citations are always checked, even on decisions without actions, and every
  unloaded citation is its own finding. A
  citation of a clause the engine did not load rejects the whole decision: `draft_citation` if
  the clause exists as a draft, otherwise `unknown_citation`. A wrong role or time is
  `wrong_role_or_time`. All are findings, logged under the role the orchestrator asked.
- **Action level.** The action must be in the role's allowed set. `share_incident_status` needs a
  fact the sender knows. It is rejected if the category is outside the recipient's boundary
  (`outside_recipient_boundary`), and a role cannot target itself (`self_target`).
  `request_information` needs a `data_category` that is a scenario category
  (`unknown_data_category` otherwise; clause categories are checked the same way at load). A
  request is accepted even for a category outside the requester's own boundary: asking is evidence
  of the need, and the boundary is enforced when anything is delivered.
- **Restrictions (`restricted_by_clause`), on every action.** A prohibition applies to its
  action; if it names a data category, it applies when the action touches that category, or when
  the action names none (conservative). A data safeguard restricts its action for its category.
  A safeguard without a data category (e.g. human oversight) is a protective duty, not a ban. `roles.yaml` preconditions are checked:
  `requires_prior`, `requires_information`, and `requires_authority`.
- **Authority.** An obligation or permission clause naming the role (or `any`) counts if it is
  binding, or if it is an illustrative scenario rule (`binding: false`). A clause with
  `binding: unknown` gives only `authority_uncertain`. Non-binding guidance never counts. The
  same firmness rule decides which obligations count as triggers.
  `stated` and `interpreted` readings are treated the same.
- Accepted effects: shares deliver the fact (boundary checked again), obligations with the same
  role (or `any`) and action are fulfilled, and goals are met. Every step is appended to the log.

## Diagnosis (`engine/diagnosis.py`)

| Category | Raised when |
|---|---|
| Information deadlock | A role needs a category (a knowledge goal, or an action's `requires_information`) that another role holds but that is outside its boundary or was never shared |
| Orphan duty | A goal action needs authority and no candidate role has it (an uncertain candidate is named) |
| Undefined trigger | A prerequisite action of a goal action is obliged by no loaded clause |
| Temporal infeasibility | An obligation's deadline passed unfulfilled |
| Mandate overlap | **Not detected yet.** It needs reviewed DHA/PDPL clauses to compare; deferred |

Every failure carries a qualification: "not found in the loaded clause set (...)", or
"uncertain in the loaded clause set" when only `binding: unknown` clauses were found. It is never
a confirmed legal gap. Undetermined deadlines are findings, not failures. The CLI prints every
clause id with its status label.

## Threat model

Agents run in the same Python process. The engine never hands them the state, and everything
they return is re-validated, but Python cannot stop deliberate introspection (e.g. walking the
call stack) by in-process code. Scripted agents are trusted test code; Phase 5 LLM agents return
only JSON. Whether untrusted agents must run in a separate process is a question for the human.

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
