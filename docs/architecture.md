# Architecture

```
policies/sources/*.pdf ──extract──> policies/extracted/*.jsonl ──(agent drafts, human reviews)──>
policies/reviewed/*.yaml ──knowledge/loader──> engine clauses (reviewed + illustrative)

scenarios/<id>/{scenario,roles,scripted_decisions}.yaml ──simulation/loader──> Scenario, RoleSet

simulation/orchestrator  (deterministic code, not an agent)
  for each inject:
    engine.release(event)                    facts, obligations, missed deadlines
    view = boundaries.view_for(state, role)  frozen, boundary-filtered
    decision = agent.observe(view)           agents/scripted (Phase 5: agents/llm)
    engine.process(decision)                 engine/constraints: accept/reject, apply
  engine.close(); graph = engine/graph.build_graph(); failures = engine/diagnosis.diagnose()
```

- **Only `engine/` and `simulation/state.py` change state.** Agents get a `RoleView`, never the
  state. They return `AgentDecision`s, which are proposals only.
- **Clauses enter the engine only through `normalized` readings** (`basis: stated |
  interpreted`). Each clause is shown with `PolicyClause.status_label`, e.g. "reviewed
  (interpreted)".
- **Determinism.** Fixed role order, all views built before any decision is applied, no clock
  or randomness. The same inputs give the same log, failures and graph.
- **Graph** (`engine/graph.py`, NetworkX). Nodes are roles, data categories, actions, clauses and
  goals. Edges are sees, holds, may, authorises, obliges, restricts, binds, needs_info,
  needs_prior and achieves. Diagnosis reads it, and the Phase 4 UI will draw it.
- **Repairs (Phase 3).** `engine/repair_search.py` builds candidate edits from the diagnosed
  failures (closed grammar, `domain/repairs.py`), discards any that would lift a restriction,
  and ranks the rest by replay. `simulation/replay.py` applies a repair as hypothetical rules
  (`repair.<edit id>`, illustrative), trigger events and one boundary widening, then reruns the
  identical incident through the same orchestrator. `storage/audit.py` (DuckDB) records runs
  and comparisons; `storage/export.py` writes JSON and Markdown.

```
baseline = run(...) ──> diagnose ──> repair_search.candidate_edits ──> hard filter
  └─> for each repair: replay.apply_repair ──> run(...) ──> ReplayComparison ──> rank
```

Specs: `specs/001-domain-and-scenario.md`, `specs/002-engine-and-diagnosis.md`,
`specs/003-repair-and-replay.md`.
