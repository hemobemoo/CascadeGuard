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
- **c. Repair ladder.** Top 3; the rest behind "Show all N" (shown or hidden in place).
- **d. Cascade graph.** Everything outside the highlighted subgraph is faded (node opacity
  0.15, no label; edges 0.06); "Show all at full opacity" turns that off. The default
  highlight is still "all diagnosed failures", so the default view is every failure's
  subgraph with the unrelated nodes faded. A right margin keeps goal names readable.
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

| Click | Phase 6 (2026-10-27) | Phase 6b | Budget |
|---|---|---|---|
| First meaningful paint | 703 ms | 382-633 ms | < 1,500 ms |
| Stepper a → b | 117 ms | 79 ms | < 200 ms |
| Swimlane cell → role view | 119 ms | 90 ms | < 200 ms |
| Swimlanes baseline → replay | 158 ms | 103 ms | < 200 ms |
| Graph highlight | 190 ms | 112 ms | < 200 ms |
| Graph: show all at full opacity (new) | — | 70 ms | < 200 ms |
| Ladder: Show all N (new) | — | 84 ms (179 ms before building every rung once) | < 200 ms |
| Compare → split screen | 186 ms | 97 ms | < 200 ms |
| Agents Scripted → LLM (cached only) | 176 ms | 185 ms | < 200 ms |

The same machine was busy to different degrees across runs; every median passed without a
re-measure. The full check passed with 434 tests at factor 1.

## Screenshots

Before (Phase 6 on `main`, `883fb43`) and after, same script, 1400×1000, Guided mode:
`before-viewport.png` / `after-viewport.png`, `before-a.png` … `before-f.png` /
`after-a.png` … `after-f.png`, and `before-expert-full-page.png` / `after-expert-full-page.png`
(Expert mode, raw ids shown).
