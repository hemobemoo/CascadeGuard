# 006b — Demo UI polish (Phase 6b, addendum to spec 006)

**Goal.** A judge-facing polish pass over the Phase 6 UI: people read names and sentences, not
ids. Display only: no engine change, no change to what any agent sees, no new dependency.
Everything in spec 006 still holds: every clause shows its status label verbatim; agent text
only under "agent statement (unverified; not a finding or a legal conclusion)"; masked,
inconclusive, overdue, open-at-end, requires-authorization and badge labels from engine
constants; `view_model` formatting-only; local assets; the same perf budgets and `perf` test.

## a. Display names

- Roles already have a `name` in `roles.yaml` (e.g. "Health Service Operator"); the UI uses it.
  It is not changed: it is part of every LLM view, so editing it would change cache keys.
- New file `scenarios/<id>/display.yaml` (read by `ui/` only, never by the engine, agents or
  exports) with human-readable labels for data categories, actions and recovery goals, and the
  incident summary (e below). Shape:

  ```yaml
  categories: {network_incident_status: "Network incident status", ...}
  actions: {reverse_automated_lockouts: "Reverse automated lockouts", ...}
  goals: {patient_access_restored: "Patient access restored", ...}
  incident_summary: "..."
  ```

  Validated on load: every key must be an id the scenario defines, every category, action and
  goal the scenario uses must have a label, values are plain text. A missing or invalid file is
  a clear error, never a silent fallback to ids.
- Where shown: names in the verdict strip, swimlane headers, role views, diagnosis cards,
  ladder, split screen and graph node labels. The raw id goes in small print or a tooltip in
  Guided mode, and is shown in full in Expert mode. Clause ids and status labels stay verbatim
  everywhere; exports (Markdown/JSON) are unchanged and keep ids.

## b. Repairs in plain language

Each edit is one sentence built only from its typed parameters and the labels above, one
template per operation (the five closed types), in `view_model`:

| Operation | Sentence |
|---|---|
| assign_owner | "Assign {action} to {role}, {deadline}-minute deadline" |
| add_escalation_trigger | "{role} must {action} when {event title}[, within {deadline} minutes]" |
| define_minimum_data_share | "Allow {role} to share {category} with {counterpart} (minimum data share)" |
| add_fallback_channel | "{role} must {action} when {event title}[, within {deadline} minutes]" |
| designate_decision_requester | "{role} requests a determination on {action} from {counterpart}[ when {event title}, within {deadline} minutes]" |

The wording follows what the hypothetical rule creates (obligation vs permission, from
`simulation/replay.py`), never more. The repair id is shown below in small monospace. A test
checks one sentence per operation and that every parameter appears in it.

## c. Repair ladder

Show the top 3 rungs; the rest behind "Show all N" (N = ranked count). Discarded and
inconclusive repairs stay listed as today, collapsed in the same way. Selecting a rung beyond
the third (e.g. from the graph or an export) expands the list first.

## d. Cascade graph

By default only the selected failure's subgraph (the nodes and edges it cites) is at full
opacity; everything else is faded. With "all diagnosed failures" selected, all are at full
opacity. A toggle "Show all at full opacity" turns the fading off. Still one chart, updated
via `chart.options`; never rebuilt.

## e. Incident summary

One sentence above the verdict strip, from `display.yaml` `incident_summary`: synthetic,
labelled as a hypothetical scenario, no legal claims and no statement of a gap (gate 7). The
evidence-auditor checks the wording.

## Tests and evidence

- Unit: `display.yaml` validation (unknown id, missing label, wrong type), one sentence per
  operation, labels used in rows, raw ids kept in Expert rows, the LLM `render_view` output
  for every role unchanged by `display.yaml` (cache keys unchanged).
- e2e: guided flow with names, "Show all N", subgraph fading and toggle, incident summary,
  Expert shows ids; budgets as in spec 006.
- Before/after screenshots in `docs/review/phase-6b-polish/`.

## Done when

The guided flow passes in the browser with scripted and cached LLM agents showing names,
sentences, the top-3 ladder, the faded subgraph and the summary; the perf budgets pass in CI;
and all checks pass.

## Human decisions (2026-10-27)

1. Labels go in a UI-only `scenarios/<id>/display.yaml`, as specified. Conditions:
   1. A test fails if any engine, agent, simulation or export module reads `display.yaml`.
   2. `display.yaml` is excluded from any scenario hash or manifest, and the scenario loader
      tolerates it. Checked 2026-10-27: there is no scenario hash or manifest; the loader reads
      `scenario.yaml`, `roles.yaml` and `scripted_decisions.yaml` by name; the LLM cache key
      hashes the role's boundary-filtered view, and digests exist only for clauses. A test pins
      both (the loader with `display.yaml` present, and runs unchanged by its contents).
   3. Labels are pure renames only (no added meaning, status or legal claim). The
      evidence-auditor checks `display.yaml` under gate 7, the same as the incident summary.
2. Role names: the existing `name` field, unchanged (e.g. "Health Service Operator").
3. Incident summary: drafted by the agent within the gate-7 constraints; the human approves
   the final wording before merge.
