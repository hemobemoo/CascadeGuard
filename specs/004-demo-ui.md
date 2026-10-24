# 004 — Demo UI (Phase 4)

**Goal.** One NiceGUI page that walks through the demo: scenario → timeline → role views →
diagnosis graph → ranked repairs → baseline vs replay → export. Scripted agents only, no LLM.

```bash
uv run python -m cascadeguard.ui.app      # http://localhost:8765
```

## Screen (one page, top to bottom)

1. **Banner (always visible):** "Hypothetical scenario, synthetic data only. Decision support,
   not legal interpretation." Clause set label (e.g. reviewed + illustrative).
2. **Scenario picker** (`scenarios/*`) and **Run baseline**.
3. **Timeline:** one row per inject (T+00 … T+75) with its title and recipients; below it the
   accepted and rejected actions, obligations and goals for that minute, as in the CLI.
4. **Role views:** pick a role and an inject; show exactly the `RoleView` the agent received
   (inject text if a recipient, decision points, facts, clauses with labels, own history), and
   which data categories are inside and outside its boundary. Nothing else.
5. **Dependency graph** (`ui.echart`, graph series; `ui.echarts` in older docs): roles,
   actions, categories, clauses. Nodes and edges named by a diagnosed failure are highlighted;
   a click on a failure in the list highlights only that one.
6. **Repairs:** ranked list (rank, edits, outcome, blockers removed, masked, new conflicts with
   tags, requires authorization) and, separately, discarded repairs with reason and clauses.
7. **Baseline vs replay** for the selected repair: goals, failures (removed / masked /
   remaining / new), changed actions, side by side.
8. **Export:** JSON and Markdown downloads, the same content as the CLI `--export`.

## Labels the UI always shows

- The status label next to every clause id (`PolicyClause.status_label`, e.g. "draft
  (interpreted)"); drafts never appear as reviewed.
- "hypothetical repair rule (not a source clause)" on every repair rule; "requires
  authorization" where set.
- Masked blockers as "masked (goal met another way)", never as removed.
- `scripted_agent_limit` tags with their one-line explanation.
- Agent text only under "agent statement (unverified; not a finding or a legal conclusion)";
  gap claims always with their citations and the fixed qualification.

## Boundary

The UI only displays engine results. `ui/view_model.py` turns `RunResult`, `SearchResult` and
`ReplayComparison` into display rows (formatting only, no decisions); `ui/app.py` renders them.
Engine-side additions, each tested: the orchestrator records the view each role received
(`RunResult.views`), and `engine/graph.py` returns the graph as plain nodes and edges. Labels
come from the engine and `storage/export.py`, never from UI code.

## Tests

- `tests/unit/test_view_model.py`: every label rule above, on the real run and on synthetic
  hostile agent text (no browser).
- Playwright MCP, end to end: pick scenario, run baseline, open the top repair, compare,
  export; screenshots of each main screen for the report.

## Questions for the human

1. NiceGUI's `User` test fixture needs `pytest-asyncio` (not on the AGENTS.md list). Add it
   as a dev dependency, or rely on the view-model tests plus Playwright? Default: no new
   dependency.
2. Export as browser downloads (default) or also written to `data/exports/`?

## Done when

The full flow works in the browser with scripted agents; checks and CI pass; the review loop
has run (its first test-breaker round covers 5747e23, f6ea214, 4f56dbe); screenshots are in the
report. No merge before the human has seen them.
