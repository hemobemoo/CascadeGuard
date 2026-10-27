# Phase 6b — Demo UI polish: before / after

Spec: `specs/006b-demo-ui-polish.md` (approved with the human's decisions, 2026-10-27).
Display only: no change to the engine, the agents, the simulation or the exports.

## What changed

- **a. Display names.** `scenarios/uae_health_access/display.yaml` (UI-only) labels the 8 data
  categories, 17 actions and 3 goals, and holds the incident summary. Role names are
  `roles.yaml` `name`, unchanged. Names appear in the verdict, swimlanes, role views, the graph,
  diagnosis cards, the ladder and the split screen. Raw ids are kept: tooltips and small print
  in Guided mode, and shown in full in Expert mode (one body class, nothing rebuilt). Clause ids
  and status labels are verbatim everywhere. The engine's own text (failure descriptions,
  outcome wording, reason codes, labelled failure lines) is unchanged and keeps its ids.
- **b. Repairs in plain language.** One sentence per edit from its typed parameters (one
  template per operation), with the repair id below in small monospace.
- **c. Repair ladder.** Top 3 of each list (ranked, inconclusive, discarded); the rest behind
  "Show all N" (shown or hidden in place).
- **d. Cascade graph.** It opens on the first diagnosed failure, with everything outside its
  subgraph faded (node opacity 0.15, no label; edges 0.06); "Show all at full opacity" turns
  that off, and "all diagnosed failures" shows every node at full opacity. A right margin
  keeps goal names readable.
- **e. Incident summary.** One sentence above the verdict strip, from `display.yaml`
  (draft for the human's approval before merge).

## Human conditions (2026-10-27)

- 1.1: `tests/unit/test_display_labels.py` fails if any module outside `ui/` names
  `display.yaml` or imports the UI (static), and if replacing `display.yaml` with unparseable
  text changes the scenario load, the baseline, any agent view (so any LLM cache key), the
  repair search or the exports (dynamic).
- 1.2: there is no scenario hash or manifest; the loader reads `scenario.yaml`, `roles.yaml` and
  `scripted_decisions.yaml` by name and tolerates `display.yaml` (same test).
- 1.3: labels are pure renames; the evidence-auditor checks `display.yaml` and the summary.

## Performance (budget test, factor 1, median of 5 after a warm-up, this machine)

| Click | Phase 6 (2026-10-27) | Phase 6b (after round 1 fixes) | Budget |
|---|---|---|---|
| First meaningful paint | 703 ms | 362 ms | < 1,500 ms |
| Stepper a → b | 117 ms | 79 ms | < 200 ms |
| Swimlane cell → role view | 119 ms | 86 ms | < 200 ms |
| Swimlanes baseline → replay | 158 ms | 80 ms | < 200 ms |
| Graph highlight | 190 ms | 86 ms | < 200 ms |
| Graph: show all at full opacity (new) | — | 55 ms | < 200 ms |
| Ladder: Show all N (new) | — | 71 ms (179 ms before building every row once) | < 200 ms |
| Compare → split screen | 186 ms | 82 ms | < 200 ms |
| Agents Scripted → LLM (cached only) | 176 ms | 81 ms | < 200 ms |

Machine load differs between runs (an earlier 6b run gave 70-185 ms); every median passed
without a re-measure. The full check passed with 443 tests at factor 1.

## LLM agents (cached only)

- e2e `test_guided_flow_with_cached_llm_agents`: a decision cache recorded from the scripted
  decisions through a stand-in client (no API call, temp directory, never `data/`), read
  offline: names, labelled sentences, the faded graph, top-3 ladder, summary, and the
  scripted-vs-LLM row. `test_inconclusive_rows_collapse_with_the_ladder` caches only the
  baseline, so replays are inconclusive and their rows collapse.
- Playwright MCP run against the real local cache (2026-10-27): "top-ranked repair (partial)"
  with labelled sentences, 1 ranked and 20 inconclusive (3 shown, "Show all 21"), the split
  screen with names and the recorded finding: `after-e-llm.png`, `after-f-llm.png`.

## Screenshots

Before (Phase 6 on `main`, `883fb43`) and after, same script, 1400×1000, Guided mode:
`before-viewport.png` / `after-viewport.png`, `before-a.png` … `before-f.png` /
`after-a.png` … `after-f.png`, and `before-expert-full-page.png` / `after-expert-full-page.png`
(Expert mode, raw ids shown). Also `after-c-one-failure.png` (one failure highlighted, the rest
faded; Playwright MCP run) and the two LLM screenshots above.

## Review loop

- **Round 1.** evidence-auditor PASS (triage `docs/review/phase-6b-clause-triage.md`; MINOR
  fixed: every repair sentence now carries the hypothetical label; MINOR deferred: the
  `uae.telecom-law.art6` notes wording, a clause file outside this display-only phase).
  phase-auditor FAIL (MAJOR: the cached-LLM half of Done-when unproven; fixed with the two e2e
  tests and the MCP run above; MINORs fixed: hidden-rung expansion, inconclusive and discarded
  collapse, split-screen names, PROGRESS state). test-breaker FAIL (MAJOR: "all diagnosed
  failures" was faded against the spec, and the perf reset relied on it; fixed, with a unit
  test; MAJOR: no cached-LLM e2e, fixed; MINORs fixed: duplicate keys, shared labels and markup
  in display.yaml rejected; QUESTION answered by labelling every sentence).
