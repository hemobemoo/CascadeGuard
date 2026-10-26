# Phase 6 — Demo UI v2: before / after

Spec: `specs/006-demo-ui-v2.md` (approved 2026-10-26). Localhost, Chromium (Playwright),
1400×1000, scripted agents, fresh server. Two methods:

- **Back-to-back script** (same as "before"): median of 3 runs, each run a new browser context;
  clicks follow each other with no pause. "Before" is the Phase 4 UI on `main` (`425ad8b`).
- **Budget test** (`tests/e2e/test_ui_flow.py::test_performance_budget`): median of 5 after one
  warm-up, 500 ms after the previous click; budget × `CASCADEGUARD_PERF_FACTOR` (default 1,
  CI 3). This is the check that enforces spec 006.

Machine load differed: the server started in 2.3 s for the "before" run and in 4.2 s for the
final "after" run (other applications busy), so the after numbers are, if anything, pessimistic.

| Measurement | Before (script) | After (script) | After (budget test, factor 1) | Budget |
|---|---|---|---|---|
| First meaningful content | 1,276 ms (load 352 + "Run baseline" click 924) | **588 ms**, no click | **700 ms** | < 1,500 ms |
| Repair list | "Find repairs" click: 883 ms | precomputed; stepper d→e **111 ms** | — | < 200 ms |
| Compare a repair | 284 ms | **124 ms** | **129 ms** | < 200 ms |
| Role view for another inject | 228 ms (inject select) | **147 ms** (swimlane cell) | **91 ms** | < 200 ms |
| Graph highlight | 125 ms (one click) | 217 ms (dropdown: two clicks) | **134 ms** (one click) | < 200 ms |
| Stepper a→b (right after load) | n/a | 192 ms | **95 ms** | < 200 ms |
| Stepper b→c, c→d | n/a | 166, 135 ms | — | < 200 ms |
| Swimlanes baseline → replay | n/a | 179 ms | **114 ms** | < 200 ms |
| Guided → Expert | n/a | 190 ms | — | < 200 ms |
| Agents Scripted → LLM (cache), verdict updated | n/a (re-run needed) | 221 ms | **140 ms** | < 200 ms |
| Agents LLM → Scripted, verdict updated | n/a | 150 ms | — | < 200 ms |
| Every Expert section after an agents switch (streamed after the visible update) | n/a | 637 / 965 ms | — | not a click budget |

**Open point for the human:** in the back-to-back script, two clicks are over 200 ms: the
dropdown highlight (two clicks) and the first agents switch. Both happen while the previous
click's hidden sections are still streaming in. The budget test, with a 500 ms gap between
clicks, passes every budget.

What made it fast:
- The scripted baseline and search are computed once at startup (0.25 s).
- The first paint holds only the header, the stepper and the verdict; the other sections
  stream in over the websocket.
- The graph is created once, with a fixed layered layout, and highlighted by updating its
  options.
- A click refreshes what is on screen first; hidden sections follow 300 ms later.
- The ladder rungs, swimlane cells and bars are escaped HTML blocks (DOMPurify on top) and are
  highlighted in place.
- The replay lanes are rebuilt only while they are shown.
- Exports are built only when a download button is clicked.
- NiceGUI's Tailwind runtime is off; `theme.css` defines the few utilities the page uses.

## Screenshots

Before: `before-header.png`, `before-timeline.png`, `before-role-view.png`,
`before-graph-diagnosis.png`, `before-repairs.png`, `before-comparison.png`,
`before-export.png`, `before-viewport.png`, `before-full-page.png`.

After (guided steps):
- `after-a.png`: verdict
- `after-b.png`: swimlanes (replay, with obligation bars)
- `after-c.png`: cascade graph
- `after-d.png`: diagnosis cards
- `after-e.png`: repair ladder
- `after-f.png`: split screen
- `after-g.png`: exports
- `after-f-llm.png`: the scripted vs LLM row with the recorded finding (local decision cache)

Also: `after-header.png`, `after-expert.png`, `after-viewport.png`, `after-full-page.png`,
`after-dark-full-page.png`.

## Review loop

- **evidence-auditor (round 1): PASS.** The diff changes no clause. Triage is in
  `docs/review/phase-6-clause-triage.md`: 19 CLEAN and 3 NEEDS-HUMAN-JUDGMENT (open items 3e,
  3p and 4d, unchanged).
- **test-breaker:**
  - Round 1, FAIL: two MAJORs, fixed (scripted results showing under the LLM toggle when no
    model is configured; the swimlane switch had no timed test), plus MINORs.
  - Round 2, FAIL: one MAJOR, fixed (the authorization label was missing from the verdict
    strip), plus MINORs.
- **phase-auditor:**
  - Round 1, FAIL: stale PROGRESS, fixed, plus MINORs.
  - Round 2, FAIL: a BLOCKER on the factor-1 budget's flakiness under machine load (a human
    gate), and the same authorization MAJOR, fixed.
  - Disagreement: it asked to move the badge rule into `engine/`. Not done, because spec 006
    says no engine change.
- Round 3 was not run: the open item (the local budget) is the human's decision.
- **Budget test after the fixes:** with the same code, every click took 73–91 ms in a quiet run
  and up to 201–227 ms under load. CI uses factor 3.
