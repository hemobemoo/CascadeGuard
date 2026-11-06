# ITU-T Y.3172 mapping (draft)

> Moved from `docs/submission-readiness.md` §7 on 2026-11-06 (Task 5, docs reconciliation),
> unchanged in meaning: the table and text below are the audit of 2026-10-29 as written there.
> The readiness file keeps a pointer here. **CascadeGuard does not claim compliance with ITU-T Y.3172:** it uses the
> Recommendation's architecture pattern (see the honest limit at the end).

Y.3172 (06/2019) defines ML pipeline nodes (clause 7):
- SRC, the data source;
- C, the collector;
- PP, the preprocessor;
- M, the model;
- P, the policy node, with rules that safeguard the underlay network;
- D, the distributor;
- SINK, the target of the ML output.

It also defines:
- the **MLFO**, which manages and orchestrates the pipeline nodes "based on ML Intent";
- the **ML sandbox**, "an isolated domain which allows the hosting of separate ML pipelines to
  train, test and evaluate them before deploying them" (p.21 of the PDF);
- the **ML underlay networks**, real or simulated.

| Y.3172 component | CascadeGuard element | Evidenced in code | Note |
|---|---|---|---|
| ML underlay network (simulated) | The synthetic incident world: the telecom network, the health portal and their two AI systems | Yes: `scenarios/uae_health_access/scenario.yaml`, `src/cascadeguard/simulation/state.py` | Simulated, synthetic only |
| SRC | Scenario injects and their facts (T+00 … T+75) | Yes: `scenario.yaml`, `src/cascadeguard/simulation/loader.py` | |
| C (collector) | Per-inject collection of the facts each role may see | Yes: `src/cascadeguard/simulation/boundaries.py` (`RoleView`) | |
| PP (preprocessor) | Boundary filtering, role-scoped clause retrieval, canonical view | Yes: `boundaries.py`, `knowledge/retrieval.py` (`clauses_for_role`), `agents/cache.py` (`canonical_view`) | |
| M (model) | The role agents (scripted or LLM) returning `AgentDecision` | Yes: `src/cascadeguard/agents/scripted.py`, `agents/llm.py` | LLM at temperature 0, cached |
| P (policy) | The deterministic engine: citation, authority, prohibition and safeguard checks, and the hard filter on repairs | Yes: `src/cascadeguard/engine/constraints.py`, `engine/repair_search.py` | The strongest correspondence: policy gates every output before it reaches the underlay |
| D (distributor) | Applies accepted actions and releases facts to recipients | Yes: `src/cascadeguard/simulation/orchestrator.py`, `state.py` | |
| SINK | Goals, obligations and diagnosed failures, shown in the CLI, UI, exports and audit | Yes: `engine/diagnosis.py`, `ui/`, `storage/export.py`, `storage/audit.py` | |
| MLFO | The deterministic orchestrator (step order, view building, decision application) and the repair search driving replays | Partly: `simulation/orchestrator.py`, `engine/repair_search.py` | There is no ML-intent input. The nearest equivalent is the scenario's critical goals plus the closed repair grammar. |
| ML sandbox | Identical-incident replay with a candidate repair, evaluated before anything is recommended | Yes: `src/cascadeguard/simulation/replay.py`, `engine/repair_search.py` | A repair is tested in replay, never applied to the baseline |
| ML intent | Scenario critical goals (`patient_access_restored`, `alert_cause_known_to_health`) | Partly: `scenario.yaml` goals | Not expressed in the Y.3172 intent format |
| Management subsystem / monitoring | Audit trail and evaluation outputs | Partly: `storage/audit.py`, `docs/evaluation/` | |

Honest limit: Y.3172 is about ML pipelines in future networks. CascadeGuard uses its
*architecture pattern* (pipeline nodes, policy node, sandbox, orchestrator) for an
institutional decision pipeline. It does not deploy ML models into a network. Say so in the
report.
