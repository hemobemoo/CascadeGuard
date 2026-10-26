# 006 — Demo UI v2 (Phase 6)

**Goal.** The NiceGUI page becomes the judge-facing product: one narrative, clearly
CascadeGuard, fast, offline. NiceGUI only (no JS frontend), no new dependency, no engine change.
`ui/view_model.py` stays formatting-only; `ui/app.py` renders. Labels come from engine and
export constants only (status, hypothetical repair rule, masked, inconclusive, overdue,
open at incident end, requires authorization, agent statement).

## Layout (one page, in this order; each section an `@ui.refreshable`)

- **Header (persistent):** CascadeGuard wordmark, scenario, agents (Scripted | LLM (cached
  only)), mode (Guided | Expert), light/dark; the disclaimer and clause-set label always visible.
- **a. Verdict strip:** baseline vs best replay: outcome with its definition, critical goals
  met (n/N), diagnosed failures, removed / masked / remaining counts, invalid_output caveat.
- **b. Timeline swimlanes:** one lane per role, columns T+00…T+75. Each cell: facts that reached
  the role (category chip; outside-boundary categories never shown), accepted / rejected
  actions, agent statements (labelled, collapsed). Under each lane, its obligations as bars
  opened → due (or "due undetermined") with state fulfilled / overdue / open at incident end
  and the source's status label. Baseline / replay switch shows the same for the replay.
  Clicking a cell opens that role's exact `RoleView` (Expert).
- **c. Cascade graph** (`ui.echart`, created once): selecting a failure changes
  `chart.options` in place and calls `chart.update()`; never rebuilt.
- **d. Diagnosis:** one card per failure category (five, empty ones say "none found"), each
  failure with description, qualification and evidence chips (clause id + status colour/label).
- **e. Repair ladder:** ranked repairs; rank 1 badged "smallest safe repair" (only if clean and
  complete); edits, roles touched, "requires authorization"; discarded (with reason, clauses);
  inconclusive listed after, unranked.
- **f. Split screen** baseline | replay for the selected repair: goals, removed / masked /
  remaining (with overdue / open-at-end labels) / new conflicts, outcome definition, caveat,
  changed actions. In LLM mode, a "same repair, scripted vs LLM" row shows both verdicts (e.g.
  resolved vs partial) and, when a recorded evaluation finding matches that repair and those
  verdicts, its wording and source doc.
- **g. Exports** (unchanged builders) and the disclaimer repeated at the foot.

**Guided mode** (default): a stepper a → f with one sentence of narration per step, showing one
section at a time. **Expert mode:** all sections, plus clause set, findings and role views.

## Visual system

One CSS token set (`ui/theme.css`, served locally): colours, type scale, spacing, radius; light
and dark (`body.body--dark`). Fixed colour per clause status: reviewed, reviewed (interpreted),
draft, illustrative, hypothetical repair rule, not loaded; colour never replaces the text label.
Roboto and Material icons from NiceGUI's own package; no CDN, works offline.

## Performance (enforced in `tests/e2e`)

Scripted baseline and search computed once at startup and held in memory (0.25 s today); LLM
(cached only) world, baseline and search computed on first switch, held in memory, never live.
Budgets on localhost: first meaningful paint (verdict strip visible) < 1.5 s; click-to-update
(stepper, graph highlight, compare, swimlane switch, role-view cell) < 200 ms, median of 5
after one warm-up; no full-page re-render. Before (Phase 4 UI, median of 3): load 352 ms, first
content after "Run baseline" 1,276 ms, find repairs 883 ms, compare 284 ms, inject switch
228 ms, graph highlight 125 ms. Screenshots: `docs/review/phase-6-ui/before-*.png`, `after-*.png`.

## Tests

`test_view_model.py`: swimlane rows, obligation bars and states, verdict strip, ladder badge,
category cards, every label from engine constants. `tests/e2e/test_ui_flow.py`: guided flow
a → f, expert mode, exports equal to the CLI's, LLM (cached only) scripted-vs-LLM row, budgets.

## Questions for the human

1. "Reads the cache only" means the UI drops "LLM (live, paid calls)" (the CLI keeps live
   runs). OK?
2. Where should the evaluation finding's wording live? Proposal:
   `scenarios/uae_health_access/evaluation_findings.yaml` (repair id, prompt version, scripted
   and LLM verdicts, text, source doc), shown only when the computed verdicts match it.
3. CI runners are slower than localhost. Enforce the same budgets in CI, or in CI only check
   them with a factor (e.g. 3x) set in the workflow?
4. "Smallest safe repair" badge: only on rank 1 when clean and not inconclusive (else no badge)?
