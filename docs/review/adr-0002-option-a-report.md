# ADR 0002 option A: report

Branch `adr-0002-option-a`. Human decision 2026-10-26 (six points, recorded in
`docs/decisions/0002-repairs-reaching-llm-agents.md` and `specs/003-repair-and-replay.md`).

## What changed

- **Owner obligation.** An `assign_owner` edit carries `deadline_minutes` (default 30; in the id,
  `owner.<action>.<role>.30m`). The engine opens the owner's obligation at the first step where
  `owner_obligation_opens_when` (roles.yaml) holds, checked after every inject and every
  accepted action. For `reverse_automated_lockouts`: the owner holds `network_incident_status`,
  the lock records (`patient_account_records`) have been released, and no role has reversed the
  locks. If that never holds, no obligation opens.
- **Overdue.** A missed owner deadline is the finding `obligation_overdue`, dated exactly at
  opened_at + deadline. The repair is not discarded; the orphan duty it targets stays a
  remaining blocker (never removed or masked) and is not a new `temporal_infeasibility`
  conflict. Shown with "owner obligation overdue ..." in the CLI, Markdown and UI. Owner
  obligations only (known limitation).
- **Views and prompt.** `RoleView.open_obligations` (own role and `any`; source with status
  label, repair rules "hypothetical repair rule (not a source clause)"; opened_at, due_at,
  open/overdue). UI role-view row. Prompt `phase5-v4` adds `your_open_obligations`, no new rule.
- **Clause.** `uae.fl2-2019.art16-exceptions` reviewed by the human (commit 98cbd85).

## Goldens (scripted)

Changed only in the owner repair ids (`.30m`) and the successful replay's
`deadline_minutes: 30`. No rank, outcome, blocker count or masked list changed; both baselines
unchanged. In the owner + share replay the obligation opens at T+30, is due T+60 and is fulfilled
at T+60 by the scripted reversal; in the owner-only replay it never opens.

Tests changed to the new id or prompt pin: `tests/integration/test_repairs.py` (OWNER;
the replay-identity test also allows the obligations the repair's own rules open),
`tests/unit/test_llm_agents.py` (SUCCESS, OWNER_RULE, `PROMPT_VERSION == "phase5-v4"`),
`tests/unit/test_retrieval.py`, `tests/unit/test_view_model.py`, `tests/e2e/test_ui_flow.py`;
also `scripts/llm_replay.py` (GOLDEN).

New: `tests/unit/test_owner_obligation.py` (27 tests). Mutation check: 16 mutants (each part of
the opening condition, opens-once, check after an accepted action, overdue date, diagnosis
exemption, remaining and masked rules, YAML and owner-rule checks, view filter both ways,
prompt, Markdown label): all killed.

## LLM runs (approved; free model; `CASCADEGUARD_OUTPUT_MODE=json_object` from `.env`)

Dry run (cache only, prompt v4): 36 of 36 baseline steps uncached; replay count unknown until the
baseline is cached (then 24 of 36 replay steps changed).

| | LLM baseline (cap 72) | Golden replay owner + share (cap 50) |
|---|---|---|
| Steps decided | 36 / 36 live | 36 / 36 (12 from the cache, 24 live) |
| no_decision / invalid_output | 0 / 0 | 0 / 0 |
| Requests | 39 agent attempts (3 invalid-output retries); request retries are not counted by the CLI (known limitation) | 28 of 50 (1 request retry after HTTP 502; 3 invalid-output retries) |
| Tokens | 90,805 in / 13,289 out | 75,108 in / 10,854 out |
| Cost | 0.000000 | 0.000000 |
| Time in API calls | 738 s | 452 s (wall 458 s) |

**Baseline vs scripted:** the same 4 diagnosed failures (information deadlock on
network_incident_status, orphan duties reverse_automated_lockouts and activate_fallback_channel,
undefined trigger review_automated_lockouts), the same two critical goals unmet;
network_incident_reported met at T+0 (scripted T+45). Findings: 2 `citation_out_of_scope`
(telecom_operator citing FL 2/2019 Art 4, correctly rejected), 2 `deadline_undetermined`.

**Golden replay: LLM partial, scripted resolved.** The information deadlock is removed (the
health operator knows the network status at T+30). The owner obligation opened at T+30 and was
in the health operator's view at T+30, T+45 and T+60 (due T+60). **The operator never proposed
`reverse_automated_lockouts`**; it proposed `review_automated_lockouts` at every step from T+15
and kept `maintain_fallback_plan` and notifications. The engine recorded `obligation_overdue`
at T+60; `orphan_duty:reverse_automated_lockouts` stays a remaining blocker, with
`orphan_duty:activate_fallback_channel` and `undefined_trigger:review_automated_lockouts`.
patient_access_restored unmet. No new conflict.

So showing the obligation and its deadline (point 5: data only, no instruction) did not change
the operator's behaviour on this free model; the engine now reports the miss explicitly instead
of leaving it implicit.

## Review loop

- Round 1: evidence-auditor **PASS** (triage: `adr-0002-option-a-clause-triage.md`);
  phase-auditor **FAIL** (2 MAJOR, 4 MINOR, all fixed); test-breaker **PASS** (4 MINOR: 2 fixed
  with tests, 2 recorded as known limitations / a question for the human).
- Round 2: phase-auditor, see the PR body.

## Open for the human

- An owner obligation still open (deadline not passed) at the end of the incident window does
  not keep its orphan duty as remaining (it counts as removed, like an owner-only repair).
  Unreachable with today's 30m edits. Change it?
- Two owners for one action: a co-owner's obligation would go overdue after the other acted
  (unreachable today; known limitation).
