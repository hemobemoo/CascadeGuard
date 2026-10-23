# Spec 003 — Repair search and replay

## Goal

For each diagnosed failure, find the smallest safe repair from the closed grammar, replay the
identical incident with it, and show whether it works. CLI:

```bash
uv run cascadeguard repairs uae_health_access                 # ranked candidates + discarded
uv run cascadeguard run uae_health_access --repair <id> [--export DIR] [--audit [DB]]
```

## Repair grammar (`domain/repairs.py`)

A `RepairProposal` is one or more `RepairEdit`s; `repair_id` is the sorted edit ids joined by
`+`. An edit id names every parameter (trigger edits end in `.<event>.<deadline>m`), so two
different edits never share an id. Each edit is one of the five operation types with typed parameters only (no free text);
missing or extra parameters are rejected. Proposals are immutable (tuples).

| Operation | Parameters | Hypothetical rule in the replay |
|---|---|---|
| `assign_owner` | role, action | obligation: role is responsible for action (gives authority; no trigger) |
| `add_escalation_trigger` | role, action, trigger_event, deadline_minutes | obligation opened by trigger_event |
| `define_minimum_data_share` | role (sender), counterpart, data_category | permission to share; counterpart's boundary gains the category |
| `add_fallback_channel` | role, `activate_fallback_channel`, trigger_event, deadline_minutes | obligation opened by trigger_event |
| `designate_decision_requester` | role, action, counterpart, trigger_event, deadline_minutes | obligation to `request_determination` from counterpart |

## Replay (`simulation/replay.py`)

Identical incident: same scenario (seed, timeline, facts), same agents, same clause set. The only
changes are the repair's own: each edit becomes an illustrative clause `repair.<edit id>`
labelled "hypothetical repair rule (not a source clause)", triggers are appended to their
event's `opens_obligations`, and a data share widens one boundary by one category. Source
clauses and the input objects are never changed. The proposal is re-validated from plain data,
and each edit must name an action its role may take; a decision requester must be allowed
the action it asks about, and its counterpart must be able to issue determinations.
`deadline_minutes` is a strict integer. Agents cannot cite repair rules: a
citation must be a loaded clause from the corpus (`unknown_citation` otherwise).

A data share widens the recipient's boundary (the information model in `roles.yaml`), so facts in
that category reach it through injects it receives as well as through accepted shares; who sends
them does not matter. Candidates therefore name only the category's original holder.

## Search and judgement (`engine/repair_search.py`)

The engine judges replays: `ReplayComparison` (outcome, blockers, new conflicts) and the
ranking live in `engine/`, as AGENTS.md requires; `simulation/replay.py` only applies and reruns.

1. **Candidates** come only from the baseline: one edit per diagnosed failure and candidate role
   (information deadlock: data share from the original holder; orphan duty: owner, or fallback
   rule for `activate_fallback_channel`, plus a decision requester per determining role when only
   uncertain authority was found; undefined trigger: escalation trigger), plus a data share for
   each share the baseline held back under a restriction. Triggers use the event at which the
   role first attempted the action; the deadline is the time to the next inject.
2. **Hard filter.** An edit whose action a loaded prohibition or safeguard restricts
   (conditional or not) is discarded with the clauses: a repair never decides a condition is met.
   A data share is checked for every role as sender, because the widened boundary lets the
   category arrive from anyone. After replay, a repair is also discarded if any action the
   baseline held back under a prohibition or safeguard is accepted, or if a fact whose category
   a prohibition or safeguard names reaches a role it did not reach in the baseline.
3. **Replay** every combination of up to `MAX_EDITS = 2` safe edits.
4. **Rank** lexicographically: most critical blockers removed, fewest edits, not requiring
   authorization, fewest roles touched, fewest clauses cited, `repair_id`.

- A *critical blocker* is a baseline failure that blocks a critical goal. It counts as removed
  when the replay no longer diagnoses it ("no longer blocking"): diagnosis only explains unmet
  goals, so a failure can stop blocking because its goal is met another way (e.g. the fallback
  orphan duty once the locks are reversed). Its uncertainty in the clause set is unchanged.
- **New conflicts** are replay failures the baseline did not have; the outcome is then
  "introduces new conflict". Outcomes otherwise: resolved (every critical goal met), partial,
  no effect.
- **`requires_authorization`** is true when an edit creates a permission that no reviewed,
  binding clause already gives: a data share unless, for every role that could send the
  category once the boundary widens (allowed to share and able to see it), a reviewed, binding,
  unconditional clause for that category names that role (or `any`) and the counterpart (or
  none), or an owner,
  trigger or fallback rule for an action that requires authority the role lacks. A duty to ask
  for a determination, or to take an action that needs no authority, creates no permission.

## Known limits

- Scripted agents replay the same decisions; they do not react to a repair. A new duty that no
  scripted decision fulfils is reported as a missed obligation (`temporal_infeasibility`), as
  with every `designate_decision_requester` repair here. LLM agents (Phase 5) may react.
- Repairs are hypothetical coordination rules for the simulation, not proposals of law. Every
  repair here requires human and institutional approval before it could be adopted.

## Audit and exports

- `storage/audit.py`: DuckDB (default `data/audit.duckdb`, gitignored), append-only tables
  `runs`, `events`, `findings`, `failures`, `comparisons`, `repairs` (ranked and discarded
  candidates). Written only with `--audit` (`run`, `run --repair`, `repairs`).
- `storage/export.py`: JSON and Markdown for baselines, searches and replays. Every clause id
  carries its status label (JSON `{"id", "status"}`); every failure keeps its description and
  qualification.

## Done when

- `tests/integration/test_repairs.py` reproduces `scenarios/uae_health_access/expected_repairs.yaml`:
  the ranked search, one successful repair (owner of lock reversal + minimum status share:
  every failure cleared) and one unsuccessful repair (status share only: the information
  deadlock clears but the lockouts stay unresolved). The baseline golden still reproduces.
- The patient-record share is discarded under FL 2/2019 Art 4 and Art 16, and no replay
  releases patient records to the telecom operator.
- The search is identical across processes and hash seeds.
