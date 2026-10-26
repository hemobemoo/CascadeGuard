# Phase 6 — Demo UI v2: before / after

Spec: `specs/006-demo-ui-v2.md` (approved 2026-10-26). Localhost, Chromium (Playwright),
1400×1000, scripted agents, fresh server; each number is the median of 3 runs, each run in a
new browser context (same method before and after). "Before" is the Phase 4 UI on `main`
(`425ad8b`); "after" is `phase-6-ui`.

| Measurement | Before | After | Budget |
|---|---|---|---|
| First meaningful content | 1,276 ms (load 352 + "Run baseline" click 924) | **414 ms**, no click (verdict) | < 1,500 ms |
| Repair list | "Find repairs" click: 883 ms | precomputed; stepper to e: **74 ms** | < 200 ms |
| Compare a repair | 284 ms | **84 ms** | < 200 ms |
| Role view for another inject | 228 ms (inject select) | **92 ms** (swimlane cell) | < 200 ms |
| Graph highlight | 125 ms | **159 ms** (dropdown: 2 clicks; options updated in place) | < 200 ms |
| Stepper (a→b, b→c, c→d, d→e) | n/a | 92, 82, 79, 74 ms | < 200 ms |
| Swimlanes baseline → replay | n/a | 169 ms | < 200 ms |
| Guided → Expert | n/a | 145 ms | < 200 ms |
| Agents Scripted → LLM (cached only), verdict updated | n/a (re-run needed) | 104 ms | < 200 ms |
| Agents LLM → Scripted, verdict updated | n/a | 140 ms | < 200 ms |
| Same, every Expert section re-rendered (streamed after the visible update) | n/a | 324 / 406 ms | not a click budget |

`tests/e2e/test_ui_flow.py::test_performance_budget` enforces the budgets (median of 5 after a
warm-up; budget × `CASCADEGUARD_PERF_FACTOR`, default 1, CI 3) and prints each number. Local
run (factor 1): paint 573 ms, stepper 114, cell → role view 131, graph highlight 137, compare
162, agents switch 140 ms. CI numbers (factor 3): in the PR's CI log.

What made it fast: scripted baseline and search computed once at startup (0.25 s); first paint
holds only header, stepper and verdict, the other sections stream in over the websocket; the
graph is created once and its options updated in place; a click refreshes what is on screen
first and the hidden sections right after; the ladder and swimlane cells are highlighted in
place; exports are built only when a download button is clicked; NiceGUI's Tailwind runtime is
off (`theme.css` defines the few utilities used).

## Screenshots

Before: `before-header.png`, `before-timeline.png`, `before-role-view.png`,
`before-graph-diagnosis.png`, `before-repairs.png`, `before-comparison.png`,
`before-export.png`, `before-viewport.png`, `before-full-page.png`.

After (guided steps): `after-a.png` verdict, `after-b.png` swimlanes (replay, with obligation
bars), `after-c.png` cascade graph, `after-d.png` diagnosis cards, `after-e.png` repair
ladder, `after-f.png` split screen, `after-g.png` exports, `after-f-llm.png` scripted vs LLM
row with the recorded finding (local decision cache), `after-header.png`, `after-expert.png`,
`after-viewport.png`, `after-full-page.png`, `after-dark-full-page.png`.
