# Architecture

```
policies/sources/*.pdf ──extract──> policies/extracted/*.jsonl ──(agent drafts, human reviews)──>
policies/reviewed/*.yaml ──knowledge/loader──> engine clauses (reviewed + illustrative)
  (quotes are checked against policies/extracted/, or against policies/transcriptions/ for a page
   whose text layer is unreliable: TRANSCRIBED_SOURCES, flagged in the clause's notes)

scenarios/<id>/{scenario,roles,scripted_decisions}.yaml ──simulation/loader──> Scenario, RoleSet

simulation/orchestrator  (deterministic code, not an agent)
  for each inject:
    engine.release(event)                    facts, obligations, missed deadlines
    view = boundaries.view_for(state, role)  frozen, boundary-filtered
    decision = agent.observe(view)           agents/scripted or agents/llm (via agents/cache)
    engine.process(decision)                 engine/constraints: accept/reject, apply
  engine.close(); graph = engine/graph.build_graph(); failures = engine/diagnosis.diagnose()
```

- **Only `engine/` and `simulation/state.py` change state.** Agents get a `RoleView`, never the
  state. They return `AgentDecision`s, which are proposals only.
- **Clauses enter the engine only through `normalized` readings** (`basis: stated |
  interpreted`). Each clause is shown, to agents, the CLI, the UI and exports, with
  `PolicyClause.status_label`: status, then binding status and source type, e.g. "reviewed
  (interpreted) · binding unknown", "reviewed · binding · English translation" or "reviewed ·
  not binding · foreign precedent" ("international precedent" for OECD, UNESCO and ITU;
  illustrative clauses keep the plain "illustrative").
- **Determinism.** Fixed role order, all views built before any decision is applied, no clock
  or randomness. The same inputs give the same log, failures and graph.
- **Graph** (`engine/graph.py`, NetworkX). Nodes are roles, data categories, actions, clauses and
  goals. Edges are sees, holds, may, authorises, obliges, restricts, binds, needs_info,
  needs_prior and achieves. Diagnosis reads it, and the UI draws it.
- **Repairs (Phase 3).** `engine/repair_search.py` builds candidate edits from the diagnosed
  failures (closed grammar, `domain/repairs.py`), discards any that would lift a restriction,
  and ranks the rest by replay; `is_smallest_safe` (read-only) decides the "smallest safe
  repair" badge the UI shows (Phase 6). `simulation/replay.py` applies a repair as hypothetical rules
  (`repair.<edit id>`, illustrative), trigger events and one boundary widening, then reruns the
  identical incident through the same orchestrator. `storage/audit.py` (DuckDB) records runs
  and comparisons; `storage/export.py` writes JSON and Markdown.

```
baseline = run(...) ──> diagnose ──> repair_search.candidate_edits ──> hard filter
  └─> for each repair: replay.apply_repair ──> run(...) ──> ReplayComparison ──> rank
```

- **Demo UI (Phase 4).** `ui/app.py` (NiceGUI, port 8765 or `CASCADEGUARD_UI_PORT`) only
  renders; `ui/view_model.py` formats engine results into labelled rows, with no decisions. The
  orchestrator keeps a separately built copy of each role's view (`RunResult.views`) and each
  role's boundary (`RunResult.boundaries`) for the role-view panel. Exports reuse
  `storage/export.py`.

```
ui/app.py ──> cli.load_world / search_repairs ──> RunResult, SearchResult, ReplayComparison
          ──> ui/view_model.py (labels: status, hypothetical rule, masked, tags, agent statement)
```

- **Demo UI v2 (Phase 6, spec 006).** At startup `ui/app.py` computes each scenario's scripted
  baseline and repair search once (and, in the background, the LLM cache-only ones) and holds
  them in memory; the page opens with the verdict and streams the other sections (swimlanes,
  cascade graph, diagnosis cards, repair ladder, split screen, exports) over the websocket.
  Guided mode shows one section at a time; Expert shows all. Clicks refresh what is on screen
  first. `ui/theme.css` holds the design tokens; `scenarios/<id>/evaluation_findings.yaml`
  holds human-worded findings shown only when the computed verdicts match. The UI never makes
  live LLM calls.
- **Display names (Phase 6b, spec 006b).** `scenarios/<id>/display.yaml` holds the incident
  summary and labels for data categories, actions and goals (pure renames); role names come
  from `roles.yaml` `name`. Only `ui/app.py` reads it (validated: every id labelled, no unknown
  id); the engine, agents, simulation and exports never do, so agent views and LLM cache keys
  are unchanged (`tests/unit/test_display_labels.py`). Repair edits are shown as sentences
  built from their typed parameters, with the raw ids in small print (all of them in Expert).

- **LLM agents (Phase 5).** `agents/llm.py` plays a role with the model in `.env` (OpenRouter,
  `openai` SDK, temperature 0, strict `json_schema` built from `AgentDecision`,
  `require_parameters`, response healing off). The prompt is the role's `RoleView`, which now
  carries `role_clauses` (`knowledge/retrieval.py`: the loaded clauses the role may cite under
  the engine's 7n rule; repair rules shown as not citable). `agents/cache.py` keys each decision
  by role, view, prompt version, model and schema; a replay reuses every unchanged step. A reply
  that fails validation twice becomes `AgentDecision.no_decision`, which the engine records as a
  `no_decision` finding. `--offline` (or the UI's "LLM (cached only)") never calls the API.
  A run with missing steps is "inconclusive": never ranked or scored (`SearchResult.inconclusive`).
- **Context for LLM agents (never citable).** `knowledge/retrieval.searchable_pages` is the one
  corpus: extracted text outside `NOT_SEARCHED` and the books, then reviewed transcriptions that
  match their pin in `approvals.yaml` (`loader.reviewed_transcriptions`). `--extracted-context`
  searches it by keyword (`+extracted:<digest>`); `--kb-context` by vector (`knowledge/kb.py`,
  `+kb:<digest>`): chunks per page split at numbered headings (about 120 words, with spans),
  embedded offline through OpenRouter (`scripts/build_kb.py` → `policies/kb/`), ranked by
  reciprocal rank fusion of exact cosine over the committed vectors and the keyword score, at
  most two per document. Acceptance queries and their stored vectors: `policies/kb/acceptance.json`,
  `query_vectors.json`.
  The index digest covers chunks, model slug, dimensions, prefixes and chunk settings, not the
  vectors. Loading the index re-chunks the corpus and refuses a stale one. Neither path touches
  the scripted demo.
- **Owner obligations (ADR 0002 option A).** `replay.apply_repair` lists each owner rule in
  `Scenario.owner_obligations`. After every inject and every accepted action, the engine
  (`ConstraintEngine._open_owner_obligations`) opens the owner's obligation once the action's
  `owner_obligation_opens_when` (roles.yaml) holds; it is due `deadline_minutes` later. A missed
  one is the finding `obligation_overdue` and keeps its orphan duty as a remaining blocker in
  `ReplayComparison`. `RoleView.open_obligations` lists each role's unfulfilled obligations
  (scenario and repair, with labels); the LLM prompt (v4) shows them as `your_open_obligations`.

```
view ──> cache_key ──hit──> cached AgentDecision
              └─miss──> build_messages(view) ──> ResilientClient(pacing, backoff)
                        ──> CappedClient(cap) ──> OpenRouter ──> validate ──(1 retry)──> cache
```

Specs: `specs/001-domain-and-scenario.md`, `specs/002-engine-and-diagnosis.md`,
`specs/003-repair-and-replay.md`, `specs/004-demo-ui.md`, `specs/005-llm-agents.md`.
