# PROGRESS — CascadeGuard

Session hand-off. Read this before doing anything (see `AGENTS.md`).

## Current phase

**Phase 5 — LLM agents: merged to main via PR #6 (merge commit, branch `phase-5-llm` kept),
tagged `phase-5`** (2026-10-26, on the human's instruction). Report:
`docs/review/phase-5-report.md`. Next: ADR 0002 option A, after the human's decision.

**ADR 0002 option A: merged to main via PR #7 (merge commit, branch `adr-0002-option-a` kept),
tagged `adr-0002-a`** (2026-10-26, on the human's instruction, CI green). Report:
`docs/review/adr-0002-option-a-report.md`.

**Phase 6 — Demo UI v2: built on `phase-6-ui`, PR open, not merged (human instruction).**
Spec `specs/006-demo-ui-v2.md` (approved with the human's answers, 2026-10-26). Report and
before/after numbers and screenshots: `docs/review/phase-6-ui/README.md`.

**Open items:**
- **ADR 0002 option A:** merged (PR #7, tag `adr-0002-a`). Known limitation: two owners for
  one action (see "Known limitations").
- **`uae.fl2-2019.art16-exceptions`**: reviewed by the human (2026-10-26, commit 98cbd85).
- **Deferred MINORs** (round 4, see "Known limitations"): cache file check does not re-check
  `prompt_version`/`model_sha256` inside the file; `Usage.calls` counts agent attempts, not
  request retries.
- **Known limitation:** the gap-wording pattern flags "no authority has been triggered" (pinned
  by `test_known_limitation_gap_pattern_flags_own_inaction`).

## Done

### Phase 6 — Demo UI v2 (branch `phase-6-ui`, PR open)
- Scope decision (human, 2026-10-26): Phase 6 = Demo UI v2, tracing moves to Phase 7; recorded
  in `START_PROMPT.md` (c529306), `AGENTS.md` (Phoenix is Phase 7, 4fb2515, approved by the
  human in chat) and the structure file.
- `ui/app.py` rewritten: page opens precomputed (scripted baseline and search at startup; LLM
  cache-only in the background, per-key locks); header with scenario, agents (Scripted | LLM
  (cached only), no live mode), Guided | Expert, light/dark; sections a verdict strip, b
  timeline swimlanes with obligation bars and role views, c cascade graph (created once, fixed
  layered layout, options updated in place), d diagnosis cards per category, e repair ladder
  (badge rule below), f split screen with the scripted vs LLM row, g exports (unchanged
  builders, built on click) and the disclaimer; Expert adds clause set and findings.
  `ui/theme.css`: design tokens, light/dark, fixed clause-status colours; local assets only;
  Tailwind runtime off. `ui/view_model.py` gains formatting-only builders (verdict, swimlanes,
  bars, diagnosis cards, ladder, scripted vs LLM). No engine change.
- `scenarios/uae_health_access/evaluation_findings.yaml`: the human-worded ADR 0002 finding,
  shown only for the exact prompt version (`phase5-v4+json_object`), the same repair and
  matching computed verdicts; validated on load.
- Tests: `tests/unit/test_view_model_v2.py` (21), `tests/e2e/test_ui_flow.py` (5: guided flow
  a-f, expert, LLM cache-only row, no model configured, performance budget). CI sets
  `CASCADEGUARD_PERF_FACTOR=3`.
- Performance (details and both methods in the report): first meaningful paint 588 ms with no
  click (before: 1,276 ms after a "Run baseline" click); budget test (median of 5, factor 1):
  paint 700 ms, every click 91-140 ms. Back-to-back script: two clicks over 200 ms while hidden
  sections stream (see "Waiting on human").
- Playwright MCP demo flow run (2026-10-26): verdict on open, timeline with obligations and
  labels, replay split screen, exports, LLM (cached only) with the real local cache showing
  "resolved vs partial" and the recorded finding (`after-f-llm.png`).
- Review round 1: evidence-auditor PASS (triage `docs/review/phase-6-clause-triage.md`);
  phase-auditor FAIL (MAJOR: stale PROGRESS, fixed here; MINORs fixed: swimlane switch
  measured, bundle lock, exact prompt match, findings validation, mode-aware rerun text, spec
  test name, structure file, role-view boundary assertion); test-breaker FAIL (MAJORs fixed:
  no scripted results under the LLM toggle when no model is configured, swimlane budget
  tested; MINORs fixed: prompt match, baseline caveat with nothing ranked, bundle lock, engine
  labels, changed actions in both modes, export without selection).

Verify:

```bash
uv run python -m cascadeguard.ui.app      # http://localhost:8765, opens precomputed
uv run pytest tests/unit/test_view_model_v2.py
uv run pytest tests/e2e -s                # guided flow, budgets (prints every number)
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### ADR 0002 option A (merged via PR #7, tag `adr-0002-a`; human decision 2026-10-26)
- An owner edit carries `deadline_minutes` (default 30, in the id: `owner.<action>.<role>.30m`).
  `replay.apply_repair` lists owner rules in `Scenario.owner_obligations` (never from YAML).
  The engine opens the owner's obligation at the first step where the action's
  `owner_obligation_opens_when` (roles.yaml) holds, checked after every inject and accepted
  action: for `reverse_automated_lockouts`, the owner holds `network_incident_status` and
  `patient_account_records` (the lock records; the human asked to use the lockouts' own
  category if one exists, instead of the alert's `fraud_model_alerts`) has been released, and no
  role has reversed the locks. A missed deadline is the finding `obligation_overdue` dated at
  the deadline; the targeted orphan duty stays a remaining blocker (never removed or masked,
  not a new conflict), shown with `OVERDUE_LABEL` in CLI, Markdown and UI.
- `RoleView.open_obligations` (own role and `any`; source label; open/overdue); UI role view
  row; LLM prompt `phase5-v4` adds `your_open_obligations` only.
- Goldens regenerated (human approval): only the owner ids (`.30m`) and the successful replay's
  `deadline_minutes: 30` changed. Tests updated to the new id and prompt pin: test_repairs
  (OWNER constant; replay-identity test also allows the repair's own obligations),
  test_llm_agents (SUCCESS id, OWNER_RULE, PROMPT_VERSION pin), test_retrieval, test_view_model,
  e2e test_ui_flow, scripts/llm_replay.py.
- New tests: `tests/unit/test_owner_obligation.py` (27). Mutation check: 16 mutants of the
  opening condition, overdue finding, diagnosis, remaining/masked rule, YAML and owner-rule
  checks, view filter, prompt and Markdown label; all killed.
- `uae.fl2-2019.art16-exceptions` reviewed by the human (commit 98cbd85, approvals.yaml).
- **LLM runs (approved; free model; json_object from .env; report
  `docs/review/adr-0002-option-a-report.md`):** dry run 36/36 baseline steps uncached (v4).
  Baseline (cap 72): 36/36 decided, 0 no_decision/invalid_output, 39 agent attempts, 90.8k/13.3k
  tokens, cost 0; same 4 failures and unmet critical goals as scripted. Golden replay owner +
  share (cap 50): 24 of 36 steps changed; 28 requests (1 retry after HTTP 502), 75.1k/10.9k
  tokens, cost 0; 0 no_decision/invalid_output. **LLM partial vs scripted resolved:** the owner
  obligation opened at T+30 (due T+60) and was in the operator's view, but it never proposed
  reverse_automated_lockouts; `obligation_overdue` at T+60, orphan duty remaining. Exports:
  `data/llm_baseline_v4/`, `data/llm_replay_v4.log` (ignored).
- **Human decisions after the PR (2026-10-26):** an owner obligation still open at incident
  end keeps its orphan duty as remaining, labelled "owner obligation open at incident end" (not
  `obligation_overdue`; spec 003; tests, 3 mutants killed). LLM replay diagnosis from the cache
  only: **model behaviour** (reversal allowed, preconditions met, the engine would have accepted
  it at T+30; the obligation was in view but the agent never mentioned or acted on it);
  `docs/evaluation/adr-0002-golden-llm-replay.md`. No prompt change. Phase-auditor round 3 not
  run (human decision).
- Playwright MCP demo flow (2026-10-26): baseline, role view T+30 with the open notify
  obligation, repair search (owner .30m + share rank 1, resolved), replay comparison, exports.
- Review round 1: evidence-auditor PASS (MINORs fixed: stale lines, approval recorded; repair
  rule label kept per the human's wording, reason noted in code); phase-auditor FAIL (MAJORs:
  stale PROGRESS, no Playwright run/UI test, both fixed; MINORs fixed: overdue shown in
  Markdown/CLI/UI, ADR sections marked superseded, scripted note); test-breaker PASS (MINORs:
  YAML/owner-rule check and tests fixed; two left as questions/limitations below).

Verify:

```bash
uv run pytest tests/unit/test_owner_obligation.py
uv run cascadeguard run uae_health_access --repair owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 5 — LLM agents (merged via PR #6, tag `phase-5`)
- Review round 1 on the Phase 4 tail (a0b6342, 2f0ddc8, 9f27e4d): phase-auditor PASS,
  test-breaker PASS, evidence-auditor FAIL (2 MINOR stale notes). All MINORs fixed in dc6c7d3
  (notes, e2e scoping, graph check, view-model placeholder). Triage:
  `docs/review/phase-5-clause-triage.md`.
- `agents/llm.py` (OpenRouter via `openai`, temperature 0, strict json_schema from
  `AgentDecision`, `provider.require_parameters`, response healing explicitly disabled, one retry,
  then `AgentDecision.no_decision`), `agents/cache.py` (key: role, view, prompt version, model,
  schema; model stored only as a hash), `knowledge/retrieval.py` (role clauses by the engine's
  7n rule; `search_extracted`, books excluded, off in prompts), `RoleView.role_clauses`.
- Engine: `no_decision` finding. CLI `--agents scripted|llm`, `--offline`, `--cache`. UI toggle:
  Scripted / LLM (cached only) / LLM (live, paid calls). `scripts/llm_smoke_test.py` (one call).
- Tests: `tests/unit/test_llm_agents.py`, `tests/unit/test_retrieval.py` (fake client, no
  network), e2e toggle check; `tests/conftest.py` refuses any live client in unit and
  integration tests. The e2e UI runs as a subprocess outside conftest: in "LLM (cached
  only)" mode it reads `.env` for the model id only (overridden by a fake id) and makes no call.
  Spec: `specs/005-llm-agents.md`.
- **Review round 2 (7eaf00b).** phase-auditor FAIL: BLOCKER, no live LLM run has completed
  (human gate P5-1); MINORs fixed (live repair search refused in the UI; spec wording; the e2e
  subprocess note). test-breaker FAIL, all fixed with tests: BLOCKER, a step whose request failed
  was not cached, so a replay with the same view could call again and credit the change to the
  repair; now every outcome is fixed for the life of the cache object (one run family; request
  failures still never written to disk), mutation-checked. MAJOR, exports did not say which
  agents produced them; `RunResult.agents` / `SearchResult.agents` now in every CLI output, JSON
  and Markdown export and the audit summary (the CLI's scripted output gains one "Agents:" line,
  a deliberate change). MINORs: duplicate parameter names are invalid output (retry, then
  no_decision), never collapsed; an unreadable or mismatched cache file is a miss, not a crash.
- **Review round 3 (5192248, last round), test-breaker FAIL; fixed after the round, not
  re-reviewed, each with a test:** MAJOR, the UI's live-repair-search guard read the toggle, so
  switching it after a live baseline still ran a live search; the guard now checks the world in
  use (`cli.live_llm`), and the CLI refuses a live `repairs` / `run --repair` too. MINORs: a
  cache entry whose outcome contradicts its fields, or a stored request failure, is untrusted (a
  miss); repeated request failures are counted apart from reused steps, and the cache line says
  it covers the baseline and replays; spec wording; tests for the agents label in `search_export`
  and the audit summary.

- **Real-model runs (2026-10-24, model chosen by the human, `CASCADEGUARD_OUTPUT_MODE=json_object`
  set in the process environment because `.env` did not set it yet):**
  - Public model list checked first: `response_format`, `reasoning`, `temperature` supported;
    reasoning not mandatory.
  - Smoke call (health_service_operator, T+15): 1 call, 6.06 s, 2,643 input / 619 output
    tokens, cost 0.000000 (free model). Validated against AgentDecision; 3 citations, all
    passed the engine; 4 actions accepted, 1 share rejected (`outside_recipient_boundary`).
  - LLM baseline (uae_health_access, no repairs, cap 72): 47 requests sent (41 for steps
    written to the cache + 3 steps x 2 failed attempts), cap not reached. 31 of 36 steps
    produced a decision; 5 `no_decision` findings (3 `request_failed`, error type not kept;
    2 `invalid_output`, policy_legal_adviser T+45 and T+60). 12 `citation_out_of_scope`
    rejections (no unknown or draft citations); 1 `uncited_gap_claim`; 4 candidate gap claims
    (with the fixed qualification); 11 rejected actions (`outside_recipient_boundary`,
    `unknown_data_category`, `authority_uncertain`). About 82,900 input / 29,100 output tokens;
    total cost 0.000000; about 8.6 minutes in API calls. Export:
    `data/llm_baseline/uae_health_access-llm-baseline.{json,md}` (ignored).
  - Diagnosis vs scripted: the same 4 failures (information deadlock on
    network_incident_status, orphan duties activate_fallback_channel and
    reverse_automated_lockouts, undefined trigger review_automated_lockouts). Goals: the same
    two critical goals unmet; network_incident_reported met at T+30 (scripted T+45). Accepted
    actions: 46 LLM vs 11 scripted, 5 in common (LLM agents act more, e.g. repeated monitor /
    request_information; they never notified health-data oversight).
  - Offline replay of the LLM baseline from the cache: identical actions, goals, failures,
    obligations, fact releases and findings (33 steps reused, the 3 failed steps not cached).
  - Observation for the human (no change made): retrieval gives a role the clauses it may cite
    for its *allowed* actions, but the engine's 7n scope check uses the actions *proposed* in
    that decision; policy_legal_adviser at T+75 cited 5 clauses without proposing
    provide_policy_analysis and was rejected. Telecom roles also cited FL 2/2019 Art 4, which is
    not in their list.
- **2026-10-25 (human instructions):** baseline review written
  (`docs/evaluation/llm-baseline-review.md`, from the export and cache only). Prompt v3: citable
  clauses grouped by the proposed action that makes them citable, and the rules "every citation
  must support an action proposed in this same decision" and "analysis-only citations require
  provide_policy_analysis" (engine unchanged, still strict). Failed requests: the no_decision
  finding carries class, HTTP status and a short redacted message. **v3 baseline** (one run,
  cap 72, `CASCADEGUARD_OUTPUT_MODE=json_object` from `.env`): 37 requests, 36/36 steps
  decided, 0 no_decision (v2: 5), 1 rejected citation (v2: 12; telecom_operator citing FL Art 4,
  correctly rejected), 1 free-text gap rejection, the same 4 diagnosed failures, oversight
  notified at T+15, cost 0.000000, 85.4k / 14.1k tokens. Export `data/llm_baseline_v3/`.
  **Golden repair, single replay:** dry run 25 uncached replay steps, above 20: not run; then
  approved (cap 50) and run once with `scripts/llm_replay.py`: 47 requests, 4 of 25 live steps
  decided, 21 `request_failed` (HTTP 502, then 429 free-tier rate limit); inconclusive (details
  in `docs/review/phase-5-report.md`). Error details now drop the response headers OpenRouter
  puts in its error body. 4.18.1 recorded in the report as the engine catching an LLM error.
- **2026-10-25 (human instructions, second set):** cache audit (no request_failed on disk);
  scratchpad output with rate-limit headers checked (no key or token) and deleted; inconclusive
  verdict for any infrastructure failure (CLI, JSON, Markdown; earlier replay re-exported
  offline as "inconclusive: 21 steps failed for infrastructure reasons"; that export was later
  removed (2026-10-26): the paced rerun cached the same steps, so it can no longer be rebuilt);
  RetryPolicy pacing/backoff (15 rpm, Retry-After or 5/15/45 s, max 3 retries, daily-limit
  stop). Paced golden replay: see "Waiting on human".
- **2026-10-26 closing check and display fixes (human instructions; display, ranking and export
  code only):** complete replays are ranked first; inconclusive ones are listed after them,
  unranked, as "inconclusive: N steps missing; not comparable", with no goal or blocker counts
  (CLI, UI, JSON, Markdown; `SearchResult.inconclusive`); the scripted-agents note appears only
  when both runs were scripted; every outcome shows its definition ("resolved: all critical goals
  met; masked failures may remain"), JSON exports carry `outcome_definition` and `masked_note`,
  and "N masked failures: cause still present" sits next to the outcome; the masked label is
  "masked (goal met another way; cause still present)"; the UI shows an "Incomplete run" banner;
  changed-action lists treat a self-target as no target (display only). Golden files unchanged.
  Playwright flow re-run in both modes (LLM cache-only, no calls); 343 tests pass. ADR 0002
  decided: Phase 5 closes with C; A is the first task after Phase 5, pending the human's
  decision on when the owner obligation opens and its deadline.
- **Review round 4 (2f98197..0adff73, 2026-10-26):** phase-auditor FAIL, test-breaker FAIL,
  evidence-auditor FAIL. Fixed with tests (each headline fix mutation-checked):
  - BLOCKER/MAJOR (all three reviewers): an inconclusive single comparison was still scored.
    `ReplayComparison.summary()` now withholds goals, failure attributions and changed actions
    when steps are missing, in JSON, Markdown, CLI, UI and the audit store.
  - MAJOR: `DailyLimitReached` carried the raw provider body and was chained to the SDK error
    (headers, model id in tracebacks). Now redacted with `error_detail` and raised `from None`;
    the CLI, UI and all three scripts catch it with a fixed or redacted line.
  - MAJOR: live CLI/UI runs had no request cap, and the estimate said "up to 2 calls". Live runs
    now need `--cap` or `CASCADEGUARD_REQUEST_CAP`; the estimate says up to 8 requests per step.
  - MAJOR: a one-attempt smoke run could store `invalid_output` and a full run would reuse it
    without retrying. One-attempt invalid outputs are now kept in memory only.
  - MAJOR: `llm_replay.py` reported an inconclusive run as a hard-filter discard (fixed).
  - MINORs fixed: inconclusive replays recorded in the audit `repairs` table (rank NULL);
    the cap is checked before pacing/backoff and a retry counts only when sent (test for a
    retried 5xx using up the cap); model-id variants redacted (case, slug, without `:suffix`);
    "no complete replay to rank" wording; smoke script passes the key to redaction; report and
    review doc corrections (PR state, scripts, test count, v2 replay sentence now historical,
    accepted-action basis 46 distinct / 47 entries, decision details); Art 16 exceptions notes
    spell out the binding scope; spec and architecture updated; replay export re-exported.
- P5-3: `--extracted-context` (opt-in) adds keyword snippets of the non-book extracted PDFs,
  each labelled "context only; not citable". Off by default, because it changes every prompt
  (the cached baseline would not be reused).

Verify:

```bash
CASCADEGUARD_OUTPUT_MODE=json_object uv run cascadeguard run uae_health_access --agents llm --offline
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 4 — Demo UI (merged, PR #5, tag `phase-4`)
- `ui/app.py` (NiceGUI, port 8765 or `CASCADEGUARD_UI_PORT`): scenario picker, timeline, role
  views, dependency graph (`ui.echart`) with failures highlighted (click a failure or pick it),
  ranked and discarded repairs, baseline vs replay, JSON/Markdown downloads.
- `ui/view_model.py`: formatting only; labels come from the engine and `storage/export.py`.
- `RunResult.views` and `RunResult.boundaries` (display copies). UI and CLI share one Markdown
  export builder (`cli.baseline_markdown`, `cli.search_markdown`); all Markdown exports carry
  the disclaimer.
- Tests: `tests/unit/test_view_model.py` (labels, role views, graph highlight, byte-identical
  exports, port).

Verify:

```bash
uv run python -m cascadeguard.ui.app      # then open http://localhost:8765
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 3 — Repair and replay (branch `phase-3-repair`)
- `domain/repairs.py`: `RepairEdit` (five operation types, typed parameters only) and an
  immutable `RepairProposal` (tuples; canonical `repair_id`).
- `simulation/replay.py`: applies a repair as hypothetical rules (`repair.<edit id>`), trigger
  events and one boundary widening, reruns the identical incident, and compares
  (`ReplayComparison`: goals, failures no longer blocking / remaining / new, changed verdicts).
- `engine/repair_search.py`: candidates from diagnosed failures and restricted shares, hard
  filter (static and after replay), replay of every combination up to 2 edits, lexicographic
  ranking, `requires_authorization`.
- `storage/audit.py` (DuckDB, `--audit`), `storage/export.py` (JSON + Markdown, `--export`).
- CLI: `cascadeguard repairs <scenario>`; `cascadeguard run <scenario> --repair <id>`.
- Golden: `scenarios/uae_health_access/expected_repairs.yaml` (search + one successful and one
  unsuccessful replay, real clause set). Spec: `specs/003-repair-and-replay.md`.

Verify:

```bash
uv run cascadeguard repairs uae_health_access
uv run cascadeguard run uae_health_access --repair owner.reverse_automated_lockouts.health_service_operator.30m+share.network_incident_status.telecom_operator.health_service_operator
uv run cascadeguard run uae_health_access --repair share.network_incident_status.telecom_operator.health_service_operator
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 0 — Tooling (merged, tag `phase-0`)
uv project on Python 3.12, Ruff, Pyright (strict), pytest, CLI stub, `.env.example`, `.gitignore`
(including the two books by filename), `README.md`.

### Phase 2 — Engine with scripted agents (merged, PR #3, tag `phase-2`)
- `simulation/state.py`, `boundaries.py`, `orchestrator.py`; `engine/constraints.py`,
  `graph.py` (NetworkX), `diagnosis.py`; `agents/base.py`, `scripted.py`; `domain/findings.py`.
- Scenario data: `roles.yaml` action preconditions, `scenario.yaml` recovery goals and
  `opens_obligations`, `scripted_decisions.yaml`.
- `cascadeguard run uae_health_access [--clauses DIR]` prints the clause set (with status labels),
  timeline, accepted/rejected actions, obligations, goals, findings and diagnosed failures.
- Golden: `tests/fixtures/uae_health_access/expected_baseline.yaml` (synthetic fixtures).
  Spec: `specs/002-engine-and-diagnosis.md`; `docs/architecture.md`.

Verify:

```bash
uv run cascadeguard run uae_health_access --clauses tests/fixtures/clauses   # fixture baseline
uv run cascadeguard run uae_health_access                                    # real clause set
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 1 — Domain, policy extraction, and scenario
- **1a/1b Extraction + inventory:** `scripts/extract_pdf_text.py` → `policies/extracted/*.jsonl`
  and `_inventory.json`. Inventory table in `docs/policy-inventory.md`. Telecom Law pages 13–47
  have no extractable text (vector-outlined glyphs; OCR would be needed).
- **1c Domain:** `src/cascadeguard/domain/` (`base`, `policies`, `decisions`, `repairs`,
  `scenario`). Clause loader `src/cascadeguard/knowledge/loader.py`. Scenario loader
  `src/cascadeguard/simulation/loader.py`.
- **1d Scenario:** `scenarios/uae_health_access/` (`scenario.yaml`, `roles.yaml`, `README.md`).
- **1e Clauses:** 31 clauses in `policies/reviewed/*.yaml`: 29 `draft` (verbatim, verified against
  the extracted page by the tests) and 2 `illustrative`.
- Docs: `specs/001-domain-and-scenario.md`, `docs/policy-methodology.md`,
  `policies/reviewed/README.md`.

Verify:

```bash
uv sync
uv run python scripts/extract_pdf_text.py          # regenerates policies/extracted/ (slow: the books)
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

## Decisions

- Repair grammar = the five types in `CascadeGuard.md` §6; lexicographic ranking as in `AGENTS.md`.
- CLI uses stdlib `argparse` (no new dependency). Pyright `strict`. Ruff excludes `*.md`.
- **Health-data regime (working reading of draft clauses, pending human review):** Federal Law
  No. 2 of 2019 is treated as applicable (Art. 2). The PDPL is not assumed to apply, because
  Art. 2(2)(e) excludes health data that has its own legislation. The scenario places the portal in
  Dubai, so the DHA Health Data Protection and Confidentiality Policy is treated as applicable.
- **Information model:** facts carry a data category, a holder and a certainty. A role's boundary
  lists the categories that may ever reach it. `define_minimum_data_share` widens a boundary by
  one category.
- **Verbatim check:** clause text must appear on its cited page, ignoring whitespace. `[...]` marks
  an omission (two-column layouts, footnote markers); the pieces must appear in order.
- `document_date` may be `unknown` when the PDF prints no date (it is never guessed).
- `page` is the PDF viewer page (1-based), the same index as `policies/extracted/`; not the printed page number.
- Scenario loading lives in `simulation/loader.py` (not listed in the structure file; it is the
  natural home, and Phase 2 builds the rest of `simulation/` around it).
- Dev dependency `types-pyyaml` (PyYAML type stubs for strict Pyright): **approved by the human**.
- Telecom (2026-10-22): the two telecom rules stay illustrative (human decision). Superseded in
  part: the human then supplied an OCR copy (see the Telecom Law OCR decision below).
- Breach-reporting period for health data: **stays unknown** (human decision); the PDPL Executive
  Regulations are not added. The unknown period is itself a candidate finding.
- `[...]` gaps: a test extracts the skipped text and fails on any qualifier, modal, number or
  cross-reference unless the gap is only a footnote marker or a margin requirement ID. FL 2/2019
  Art. 4 and PDPL Art. 2(2) are now quoted in full instead of with gaps.
- `PolicyClause.binding` and `page` are strict (no "yes"/1/"3" coercion), with tests
  (phase-auditor round 2).
- **`normalized` basis (human decision 5h, 2026-10-23):** `normalized` keeps its links to
  `roles.yaml` actions and records `basis: stated | interpreted`; `interpreted` needs a one-line
  `mapping_note` (the loader rejects it otherwise). A power to regulate is never read as an
  obligation to act (such a rule becomes illustrative). The engine treats both bases the same;
  reports and the UI must show `PolicyClause.status_label` (e.g. "draft (interpreted)").
  All 14 `normalized` blocks have a basis: 12 interpreted, the 2 illustrative ones stated.
- **Telecom Law OCR (human-supplied, 2026-10-22):** a derived source in
  `policies/sources/ocr/…ocr.pdf`, extracted to its own JSONL with `"ocr": true`; the original is
  unchanged (restored in 428e114 after 0a51f82 overwrote it). Quotes from OCR pages are
  corrected against the page image and must carry "OCR — check against image" in notes (loader
  check). Provenance and known OCR errors in `docs/policy-methodology.md`.
- **Telecom illustrative rules vs. Art 12, 13, 14(3), 30** (checked against page images): none
  states an operator incident-reporting duty or deadline, so `illus.telecom.incident-report` stays
  illustrative ("the Law delegates this to TDRA regulations / the Executive Order, which are not in
  the reviewed corpus"). Art 14(5) supports the regulator's information requests; drafted as
  `uae.telecom-law.art14-5` (`interpreted`). `illus.telecom.regulator-information-request` stays
  loaded until that draft is reviewed.
- Draft clauses are not loaded by the engine. Phase 2 may be built against synthetic fixture
  clauses under `tests/fixtures/` (AGENTS.md "Human gates"); fixtures never prove the real scenario.
- **Dubai Law No. 26 of 2015 is not drafted as a clause.** Art. 3 applies it to government
  entities and to "Persons ... who are determined by the Competent Entity"; nothing in the corpus
  shows the scenario's private operators are determined. It governs dissemination and exchange of
  "Dubai Data" through the Competent Entity's platform, not an incident channel between operators,
  and Art. 13(a) is without prejudice to data legislation in force; the agent's reading is that it
  does not override FL 2/2019 Art. 16 (not a legal conclusion). **Human agreed (2026-10-22):** not drafted; kept as a candidate note only.
- **"UAE Policy Foundation.pdf" (human decision, 2026-10-22):** the compilation's issuer is
  "not printed (unofficial compilation)", date unknown. Clauses from its Charter part (pp. 1–3:
  `uae.ai-charter.safety`, `uae.ai-charter.human-oversight`) use issuer "UAE Artificial
  Intelligence, Digital Economy and Remote Work Applications Office", date 2024-07, binding false.
  The other parts and their pages are listed in `docs/policy-inventory.md`.

- **Phase 2 engine decisions (2026-10-23):** authority comes from an obligation or permission
  clause that is binding, or from an illustrative scenario rule (`binding: false`).
  `binding: unknown` gives only "authority uncertain"; non-binding guidance never gives
  authority. A citation of an unloaded clause rejects the whole decision (`draft_citation` or
  `unknown_citation`, both findings). All roles decide on the same snapshot; the engine applies
  decisions in `roles.yaml` order. Mandate overlap is not detected yet; it needs reviewed
  DHA/PDPL clauses.
- **Phase 2 review round 3 (2026-10-23, last round):** phase-auditor FAIL only on question 7o
  (no code change); test-breaker FAIL (BLOCKERs: inject text and decision points still told each
  recipient about the other organisation; a misspelt request category dodged a prohibition;
  MAJOR: clause data categories unchecked). Fixed after the round, not re-reviewed: decision
  points name one role and go only to it; inject descriptions hold only what all recipients may
  know; request and clause categories must be scenario categories (`unknown_data_category`);
  empty impostor decisions are findings; the summary lists every fact delivery and goal minute.
  Each fix has a test, mutation-checked against the old text.
- **Phase 2 review round 2 fixes (2026-10-23):** decisions re-validated from plain data
  (constructed objects and subclassed containers rejected or normalised); a share delivers
  exactly the fact it checked; no fact is released before its inject; every bad citation is a
  finding; self-targeted shares rejected; only obligation clauses open obligations, and
  `binding: unknown` ones are marked uncertain; book names refused case-insensitively and
  `source_file` must resolve inside `policies/sources`; stray files, subdirectories, extra keys
  and blank text refused; every clause id in the CLI carries its status label; fresh-process
  determinism test with three hash seeds. Requests for a category outside the requester's own
  boundary stay accepted (documented in the spec).
- **Phase 2 review round 1 fixes (2026-10-23):** inject text, decision points and clauses go only
  to the inject's recipients; views hold deep copies of facts and the state keeps private
  copies; prohibitions apply to every action kind (requests by category included); a safeguard
  without a data category is a protective duty, never a ban (engine decision, recorded in the
  spec); citations are checked before any early return; wrong role/time is a finding logged
  under the real role; obligations on `any` are fulfilled by whoever acts; only firm clauses
  are triggers. The golden summary now lists every decision-level rejection and each finding's
  minute and role (format change only, same content).
- **Phase 2 fixtures:** synthetic illustrative clauses in `tests/fixtures/clauses` reuse the draft
  clause ids and behave in the engine as those clauses would: same `normalized` reading and same
  authority/trigger outcome (binding true -> illustrative scenario rule; binding unknown kept;
  non-binding guidance carries no `normalized`). `tests/unit/test_fixtures.py` fails on drift. They are labelled "SYNTHETIC FIXTURES ... not the real corpus" in
  every output. The real-corpus golden `scenarios/uae_health_access/expected_baseline.yaml`
  was added in 392f162 after the core-set review.
- **NetworkX without stubs:** `types-networkx` is not on the AGENTS.md list, so NetworkX is
  confined to `engine/graph.py` behind typed helpers instead of adding a dependency.
- **Human decisions, 2026-10-23 (answers to "Waiting on human"):**
  - Core set **reviewed** (`status: reviewed`, commit "Reviewed by human: ..."):
    `uae.fl2-2019.art2`, `uae.pdpl.art2-2`, `uae.fl2-2019.art4`, `uae.fl2-2019.art16`,
    `uae.fl2-2019.art6`, `dha.pp11.4-18-2`, `dha.pp11.4-18-4`, `dha.pp11.4-18-1`,
    `uae.ai-charter.human-oversight`. The two telecom rules stay illustrative. The human's
    changes below were applied to these clauses before they were marked reviewed.
  - Commit 194103a confirmed: the rule changes, including auto-merge, are the approved ones.
  - 7o: the fixture-based golden is accepted for Phase 2, labelled synthetic; the real-corpus
    golden is added after the core-set review.
  - 7n: a citation must concern the citing role or its action; a mismatch rejects the decision
    and is a finding.
  - 7q: no separate process; frozen read-only views suffice for this slice (known limit).
  - 7r: reject legal-gap claims made without citations.
  - 7s: mandate-overlap detection waits for reviewed DHA and PDPL clauses; never inferred from
    fixtures.
  - 7t/7v: Art 4 and Art 16 are conditional prohibitions, not a flat ban. Where a permission or
    exception depends on conditions the engine cannot evaluate, the result is "authority
    uncertain - requires determination"; the engine never decides a condition is met.
  - 7u: `binding: unknown` on illustrative clauses is for fixtures only; a test keeps real
    clauses from it unless a human sets it.
  - 7m: a power to issue rules on requesting information is not a permission to request it in
    this incident; `uae.telecom-law.art14-5` stays interpreted with "authority uncertain"; the
    illustrative rule stays loaded.
  - h2: `dha.pp11.4-18-1` supports "a fallback plan must exist" (`maintain_fallback_plan`), not
    authority to activate it; activation authority is uncertain. `dha.pp11.4-18-5` models DHA
    only; the UAE Information Office is out of scope for this slice.
  - 7l: the human contacts GitHub Support about `refs/pull/1/head`; done for now.
  - Phase 2 round-3 fixes: no fourth review round; they are covered by tests but not
    re-reviewed, and the Phase 3 review loop covers them.
  - README: one line on source ownership with a link to each official source (added).

- **Human decisions, 2026-10-23 (second set):**
  - PR #3 merged; `main` tagged `phase-2`; Phase 3 started.
  - The post-review edit to `dha.pp11.4-18-1` stays; the edits in 9b7b7fa are accepted.
  - New gate-1 rule (rule-file change approved by the human): any edit to a `status: reviewed`
    clause sets it back to `draft` in the same commit and lists it for re-approval.
    `policies/approvals.yaml` holds the approved digest of each reviewed clause (baseline: the
    core set with the 9b7b7fa edits); `tests/unit/test_approvals.py` enforces the rule.
  - 3w: keep quoting the 2024 text. Checked on EUR-Lex (2026-10-23): Regulation (EU)
    2026/1744 (Digital Omnibus on AI, 8 July 2026, applies from 27 July 2026) amends
    Regulations 2024/1689, 2018/1139 and 2023/1230. It does not amend AI Act Art 14 or Art 73
    (it inserts Art 75(1a), a derogation from Art 73 for providers under the AI Office's
    competence), and it does not amend the GDPR, for which EUR-Lex lists only corrigenda (two
    amendment proposals, 52025PC0501 and 52025PC0837, are pending). All five `eu.*` clauses
    carry a dated "unchanged by the 2026 amendment" note; none was changed in substance.
  - 3x: the README note stays; no clause quotes `AIGuide_EN_v1-online.pdf` (inventory note).
  - Remaining open questions are collected for the end of Phase 3; none blocks it.
  - The 20 drafts stay draft; the human is told only if a Phase 3 repair needs one (none does).
- **Phase 3 engine decisions (2026-10-23):** a minimum data share widens the recipient's boundary
  (the Phase 1 information model), so it works the same whoever sends; candidates name the
  category's original holder. Search combines up to 2 edits. Repair rules are illustrative
  clauses labelled "hypothetical repair rule (not a source clause)". A failure "no longer
  blocking" may be gone only because its goal is met another way. `LogEntry.data_category`
  records the category a share or request touched (not in the golden summaries).

- **Phase 3 review round 1 (2026-10-23).** evidence-auditor PASS (MINORs fixed: EUR-Lex URL in
  the five EU notes, OECD truncation note, CLI wording, scripted uncertainty). phase-auditor FAIL
  (MAJOR: replay judgement outside `engine/`; JSON exports without labels/qualifications).
  test-breaker FAIL (BLOCKERs in Phase 2 code: 7n scope widened by disallowed actions; 7r narrow
  regex and no qualification check; MAJORs: share filter only for the named sender, share
  authorization ignored roles/conditions, repair rules citable in replays, search output lost
  labels when nothing ranked). All fixed with tests, each mutation-checked:
  `ReplayComparison` moved to `engine/repair_search.py`; scope uses allowed actions only; gap
  claims need a citation and a qualification (`unqualified_gap_claim`); citations must be corpus
  clauses; share edits checked for every sender and new restricted-category deliveries discard a
  repair; `SearchResult` carries the clause set and labels; JSON exports label every clause and
  keep qualifications; repair ids include trigger and deadline; proposals re-validated in replay;
  ScriptedAgent returns copies; `document_date` must be a real date; audit `repairs` table.
  The scripted telecom T+30 uncertainty "No clause found that authorises this share." was removed
  (an uncited gap-style line; it never appeared in a golden). Expected-repairs golden regenerated:
  only repair ids (trigger/deadline suffix) and the sorted order of one discard's clauses changed.
- **Phase 3 review round 2 (2026-10-23).** phase-auditor PASS (QUESTION-FOR-HUMAN items only:
  4a-4c; MINORs fixed: rule text, stale PROGRESS line). test-breaker FAIL: BLOCKERs (share
  authorization checked only the named sender although the widened boundary lets any role
  send; gap claims could pass with a negated qualifier or a paraphrase), MAJOR (decision
  requester `action`/`counterpart` unchecked), MINORs (non-strict deadline, decisions mutable
  between collection and processing, weak identity and patient-record tests). All fixed with
  tests, each mutation-checked: a share needs a reviewed basis for every possible sender; gap
  claims only in the structured `AgentDecision.gap_claims` (citations + fixed qualification;
  free-text gap wording rejected; `overstated_gap_claim`); requester parameters checked;
  `deadline_minutes` strict; the orchestrator copies each decision on return; identity test
  compares fact releases both ways and every agent view, for both golden repairs. Two tests
  changed on purpose with the rule: cited free-text gap analysis is now rejected (use a
  GapClaim), and a reviewed share clause naming only one sender no longer exempts a share.
  `RepairProposal.requires_authorization` is computed by the engine (`proposal()`); replay
  does not use it.
- **Phase 3 review round 3 (2026-10-23, last round).** test-breaker FAIL: BLOCKER, an agent
  could still state a legal gap in free text with wording the gap pattern misses ("UAE law
  lacks any provision ...", "the legislation is entirely mute ...") and it was stored unlabelled
  in the log and audit store; MINOR, a decision-requester repair was never marked
  requires_authorization even if requesting needed authority. Fixed after the round, not
  re-reviewed: agent rationales are stored only under the fixed label "agent statement
  (unverified; not a finding or a legal conclusion)"; only GapClaims become candidate findings;
  the requester goes through the same authority check. Mutation-checked. Remaining
  QUESTION-FOR-HUMAN items: 4a, 4b, and new 4e (new conflicts do not lower the rank).
- **Human decisions, 2026-10-24 (answers to "Waiting on human" items 3-5):**
  - **5 (round-3 gate): approach accepted.** Gaps are stated only as structured GapClaims; all
    agent free text is labelled "agent statement (unverified; not a finding or a legal
    conclusion)". No attempt to catch every wording. One final test-breaker pass, limited to
    a4b5c82 and every place agent free text is stored, exported or printed; no further rounds.
    The Phase 4 spec (`specs/004-demo-ui.md`) requires the UI to show the same label.
  - **4c:** the gate-1 rule in AGENTS.md (8333dfa) is approved.
  - **Ranking (4a, 4b, 4e)**, `CascadeGuard.md` section 6 authoritative; ADR
    `docs/decisions/0001-repair-ranking.md`, AGENTS.md and `specs/003-repair-and-replay.md`:
    hard filters; clean repairs above repairs with new conflicts; within each group most
    critical blockers removed, fewest edits, fewest roles touched, fewest clauses cited; among
    repairs with new conflicts, fewest new conflicts. Agent choice: "not requiring
    authorization" and `repair_id` stay as the last tie-breaks (the human's order does not
    place the authorization tie-break). 4a: a blocker counts as removed only when its cause is
    gone; one hidden by its goal being met another way is "masked (goal met another way)".
    4e: repairs with new conflicts are ranked lower, never discarded; a conflict that is only a
    repair duty no scripted agent attempts is tagged `scripted_agent_limit` (revisit in
    Phase 5). `expected_repairs.yaml` regenerated.
  - **4d (draft mappings, clauses stay draft):** `mocai.ethics.fallback-plan` maps to
    `maintain_fallback_plan` (consistent with h2); `itu.y3172.req-ml-mng-003` has no action
    mapping (design requirement; standards and gap-analysis context); `uae.ai-charter.safety`
    has no permission mapping (non-binding principle); `uae.telecom-law.art14-5` mapping note
    rewritten to match 7m. `dha.pp11.4-18-5`: see 3p. `dha.pp11.applicability` keeps
    `binding: unknown` (3e).
  - **Evidence questions (working readings only, never legal conclusions):**
    3a protective reading: lock records linked to a health service account are treated as
    health data under FL 2/2019 Art 4 (basis interpreted), which keeps the Art 4/16 discard. The
    reviewed Art 4 clause already maps that share as interpreted; its note still says the
    question is for the human. It was **not edited**, because any edit sends a reviewed clause
    back to draft (gate 1) and the engine would drop it; update the note at its next
    re-approval. 3b: the portal operator is not assumed to be a "Health Authority"; the human
    checks the Arabic. 3c: FL 2/2019 is treated as the health data's own legislation; scenario
    assumption added to `scenarios/uae_health_access/README.md` (synthetic, non-governmental,
    DHA-licensed operator; exclusion (b) out of scope). 3d: "treated as applicable (working
    reading)" stays. 3e: `binding: unknown` stays. 3f: precedence "requires determination"; the
    unknown reporting period stays a candidate finding. 3j: the inventory may list filenames,
    page counts and title/author metadata only, never text. 3k: structure file updated.
  - **3i (DHA footers):** the extracted footers read "1/52" to "50/52" on viewer pages 1-50,
    one-to-one, with no missing or repeated number inside the copy. Footers 51/52 and 52/52 are
    missing: the copy ends on page 50 in section 5 (references, item 5.23). The drafted DHA
    clauses are on pages 1, 30, 31 and 32; none is next to the gap. The human looks for a
    complete copy.
  - **CI:** `.github/workflows/checks.yml` runs `uv sync --locked` and the full check command
    (actions/checkout, astral-sh/setup-uv; not a project dependency).
- **Final test-breaker pass (2026-10-24, FAIL), fixed after the pass, not re-reviewed:**
  BLOCKER: `ProposedAction.target` was free text for every action except share/request, and
  was stored and printed unlabelled (a gap could be stated there with no citation). MAJORs:
  unknown `action_type`, unknown share/request target, impostor `role_id` and the class name of
  a non-decision object were echoed unlabelled into the log, findings, DuckDB, JSON and CLI;
  `GapClaim.statement` became a finding without the label, and a newline in it forged a CLI
  line; the JSON export dropped a candidate gap claim's qualification. MINOR: unknown
  `data_category` echoed. Fixes: a target must be a role id for every action
  (`unknown_target` otherwise); agent strings that are not scenario ids are logged as
  `<not a scenario id; agent text withheld>`; malformed-type, unknown-target and
  unknown-category details are fixed text; rationale and gap statements are stored as
  `agent_statement(...)` (label, one line); the run JSON export adds `detail` to every finding
  and `qualification` to every candidate gap claim. `tests/unit/test_phase3_final_pass.py`
  (10 tests) fails on the old code and passes now. Not fixed (not in the human's scope, see
  "Waiting on human" 6): the OVERSTATED wording list, and `copy.deepcopy` running on agent
  output before the type check.
- **Human decisions, 2026-10-24 (follow-up to the final pass):**
  - **Ranking, two keys added** (ADR 0001, AGENTS.md, spec 003): hard filters; clean before
    new conflict; resolved (every critical goal met in the replay) before partial, then most
    critical goals met; most critical blockers removed at their cause; fewest critical
    blockers only masked; fewest edits; fewest roles; fewest clauses cited; not requiring
    authorization; `repair_id`. Among repairs with a new conflict, fewest new conflicts still
    breaks the ties left after clauses cited. Why resolved outranks blockers removed: the aim
    is a feasible recovery path, and masked blockers stay visible as findings.
    `expected_repairs.yaml` regenerated; owner + share is rank 1 again.
  - **3p: not applied.** The two clauses stay separate; the draft `dha.pp11.4-18-5` notes that
    its actor comes from 4.18.4. 3p is now part of the human's clause review.
  - **3a:** the reviewed Art 4 clause is not edited.
  - **Outside the pass scope, fixed with a test each:** OVERSTATED now also catches
    "conclusively", "definitely", "absolutely" (no further words: the label and the fixed
    qualification are the real safeguard); the orchestrator checks the type of agent output
    before deep-copying it (anything else goes to the engine uncopied and is rejected as
    malformed).
- **`RepairProposal` shape (Phase 3 decision).** `operation`/`applies_to`/`parameters` became
  `edits: tuple[RepairEdit, ...]`, because the ranking counts repair edits and a repair can need
  two (CascadeGuard.md section 6, "Repair 2"). Each edit keeps one closed operation type with
  typed parameters.

- **Phase 4 review round 1 (2026-10-24), test-breaker on 5747e23, f6ea214, 4f56dbe: FAIL.**
  BLOCKER: a cited clause id outside the corpus (decision or GapClaim citation) was stored and
  printed verbatim, so invented text and a forged CLI line reached every output. Fixed: such
  ids are shown as `<not a scenario id; agent text withheld>` everywhere (the existing test for
  unknown citations now expects that placeholder instead of the invented id, a deliberate rule
  change). MINORs fixed: `agent_statement` replaces control and format characters (terminal
  escapes, zero-width and bidi marks); the orchestrator rebuilds each decision from JSON
  instead of deep-copying, so a foreign object inside a `model_construct` decision runs no
  code; a test pins "not requiring authorization" after clauses cited. MINOR not fixed (human
  decision: no further words): OVERSTATED is a word list and is bypassed by homoglyphs or
  synonyms; the label and fixed qualification remain the safeguard.

- **Phase 4 human decisions (2026-10-24):** spec 004 approved as written; no pytest-asyncio;
  exports as browser downloads only (the CLI `--export` writes to disk); CascadeGuard.md
  section 6 sentence replaced with the human's wording (fbc51e1, own commit); README gives the
  port and `CASCADEGUARD_UI_PORT`; the next test-breaker round covers 0e76c21 first (done in
  round 2: the WITHHELD and control-character fixes hold).
- **Phase 4 review round 2 (2026-10-24).** evidence-auditor PASS (triage in
  `docs/review/phase-4-clause-triage.md`). test-breaker FAIL: MAJOR, no repeatable test proves
  the browser flow (human gate, below); MINORs fixed with tests: `_copy` now checks every nested
  value for an exact plain type before serialising (a `model_serializer`, generator, custom
  `__getattribute__`, custom tzinfo or `str` subclass runs no code and is rejected as
  malformed); UI and CLI Markdown exports are byte-identical (shared builder; test compares the
  CLI's files); the graph highlights only the selected failure, and only edges touching its
  subject (test checks a second failure's nodes are not highlighted); failures in the list are
  clickable; the banner shows the clause set. Reviewer QUESTION about AGENTS.md not matching
  the ranking: disagreement, AGENTS.md lines 46-60 already hold the human-approved order
  (f6ea214). Stale PROGRESS.md: fixed here.

- **Phase 4 review round 2, phase-auditor: PASS.** All four "Done when" items proven (it ran
  the flow itself in headless Edge on a clean export of 1e7fc22). MINORs fixed: the structure
  file lists `ui/view_model.py` (replacing the planned timeline/graph_view/replay_view modules)
  and `.claude/launch.json`; the masked, removed and requires-authorization labels are
  constants in `engine/repair_search.py` used by the CLI and the UI; the UI binds to
  127.0.0.1 only; the baseline runs off the event loop. QUESTION-FOR-HUMAN items: confirm the
  CascadeGuard.md section 6 approval in the PR, and approve or drop `.claude/launch.json`.

- **Phase 4 review round 3 (2026-10-24, last round), test-breaker: FAIL.** No probe broke a
  guarantee (hostile text, view mutation, `_copy`, determinism across hash seeds, replay
  identity all held). MAJOR 1: the view-model tests missed 9 of 12 label mutations. Fixed after
  the round, not re-reviewed: one test per display path (status labels on timeline, failure
  rows, role-view clauses and comparison targets; engine qualifications; removed label;
  `scripted_agent_limit` tag and explanation; replay notes; a role view shows only its own
  role's statements); all 9 mutants now fail the tests. MAJOR 2: no repeatable browser test
  (still human gate 0). MINORs fixed: role view filters unlabelled agent text instead of a bare
  `assert`; "outside its boundary" uses every scenario category; the role view also shows
  instructions, allowed actions and simulation time (the whole `RoleView`).

- **Phase 4 human decisions (2026-10-24, second set):**
  - Browser proof: the Python `playwright` package is a dev dependency (approved; in the
    AGENTS.md stack). `tests/e2e/test_ui_flow.py` (marker `e2e`, Chromium) drives the core
    flow: scenario and baseline, disclaimer and a clause status label, a role view, the
    top-ranked repair with "requires authorization" and the hypothetical-rule label, baseline
    vs replay, and both replay exports compared with `cli --export`. CI installs Chromium and
    always runs it; `uv run pytest -m "not e2e"` skips it locally. The test starts the UI
    without pytest's environment variables (NiceGUI switches to its own test mode otherwise).
  - Round-3 fixes accepted without another round. **The Phase 5 review covers them first**
    (a0b6342, and the Phase 4 commits after it).
  - `uae.telecom-law.art14-5`: permission mapping dropped (as in 4d); the 7m reading is in the
    notes; stays draft; `illus.telecom.regulator-information-request` stays loaded. The unit
    test now expects no authority from it.
  - CascadeGuard.md section 6 wording confirmed by the human (approved in chat 2026-10-24).
  - `.claude/launch.json` kept: no secrets, no machine-specific paths.

- **Human decisions, 2026-10-24 (Phase 5, answers to P5-1 to P5-6):**
  - **P5-1:** model chosen by the human; it has JSON mode. New setting
    `CASCADEGUARD_OUTPUT_MODE` = `json_schema` (default) | `json_object`, chosen explicitly,
    never automatic; `json_object` sends `response_format: {"type": "json_object"}` with the
    schema in the prompt; `require_parameters` stays; reasoning off; temperature 0; validation
    unchanged; the mode is in the prompt version and cache key and shown in runs and exports.
    Before the call the public model list must show `response_format` support. Then ONE smoke
    call; if it succeeds, ONE capped baseline (uae_health_access, no repairs, at most 72
    requests including retries); if it fails, stop.
  - **P5-2 acknowledged:** before the first smoke call, a test bug (`env_file` default bound at
    import) made one CLI test send 72 unapproved requests to OpenRouter (36 steps x 2 attempts),
    all failed. Fixed: `env_file` read at call time; `tests/conftest.py` clears the LLM
    variables, points `.env` at a missing file and makes building a live client an error.
  - **P5-3:** yes, after the baseline works: keyword snippets only from non-book extracted PDFs,
    labelled "context only; not citable"; citations stay reviewed/illustrative clause ids only.
  - **P5-4:** live repair search declined for now; decided after the LLM baseline.
  - **P5-5:** LLM roles see repair rules (uncitable, labelled hypothetical); lower cache reuse
    accepted.
  - **P5-6:** `run --repair <id> --agents llm` replays a single repair; before any live call it
    prints the uncached steps and needs `--live`. None run until approved.
  - Phase 5 round-3 fixes accepted without another round; the review of the real-model run
    covers them first. Do not merge; stop after the baseline report.

- **Human decision 2026-10-26 (invalid_output):** `invalid_output` stays out of the inconclusive
  rule: it is model behaviour, a defined no-decision outcome under AGENTS.md, and deterministic
  from the cache. A run with one is still ranked and scored, and every outcome shows the caveat
  "N steps with no decision (model returned invalid output): <role at time, ...>; the result may
  depend on them" (CLI, UI, JSON `invalid_output_caveat`, Markdown, audit). Recorded in spec 003.
  Paced golden replay check (cache only): the missing telecom_operator T+15 decision changed no
  view or event the health operator received from T+30 to T+75 (details in the Phase 5 report).

## Approved gate-5 exceptions

- **2026-10-22, book history purge (one time, approved by the human in chat).** Both book PDFs were
  copied to `C:\AI for Good Lab Hackathon UAE\CascadeGuard-book-backup\` (with a full
  pre-purge `git bundle` of all refs). History was rewritten with
  `uvx git-filter-repo --force --invert-paths --path-glob "*Abhivardhan*" --path-glob "*Oxford Handbook*"`
  (`--force` because this is a working clone, not a fresh one). `phase-1-domain-scenario` already
  sat on the rewritten `main` (no rebase needed); tag `phase-0` points at the rewritten Phase 0
  merge `51191ce`; branch `phase-0-tooling` deleted locally and on GitHub; `main`,
  `phase-1-domain-scenario` and `phase-0` force-pushed. `git log --all -- "*Abhivardhan*" "*Oxford*"`
  returns nothing; PR #2 head is the rewritten `d49da75`. The books stay on disk in
  `policies/sources/` (ignored). **Residual:** GitHub keeps the read-only ref `refs/pull/1/head`
  at the old commit `9f67523`, whose ancestors still contain the books; only GitHub Support can
  remove it. Other clones made before 2026-10-22 must be re-cloned.

## Minimal core set for Phase 2

The engine needs these reviewed (or confirmed illustrative) to run the real baseline. The other
clauses are precedents and context for gap analysis and can be reviewed later.

| Clause id | Why the engine needs it |
|---|---|
| `uae.fl2-2019.art2` | Establishes the applicable health-data regime |
| `uae.pdpl.art2-2` | Shows why the PDPL is not assumed to govern health data |
| `uae.fl2-2019.art4` | Prohibition: no circulation of patient data outside permitted cases |
| `uae.fl2-2019.art16` | Safeguard: patient-information confidentiality and its exceptions |
| `uae.fl2-2019.art6` | Basis for the health-data oversight role's determinations |
| `dha.pp11.4-18-2` | Alert is investigated as a suspected incident, not a proven breach |
| `dha.pp11.4-18-4` | Breach-reporting period (unknown: candidate finding) |
| `dha.pp11.4-18-1` | A continuity plan must exist (h2); activation authority uncertain |
| `uae.ai-charter.human-oversight` | Human oversight principle with no owner (orphan-duty evidence) |
| `illus.telecom.incident-report` | Already illustrative: telecom reporting duty |
| `illus.telecom.regulator-information-request` | Already illustrative: regulator's telecom remit |

## Waiting on human

**Phase 6 (2026-10-26):**
- Badge rule: is a run with `invalid_output` steps "complete" for the "smallest safe repair"
  badge? Today only infrastructure failures (inconclusive) block it (test-breaker question).
- Performance: the e2e budget passes (500 ms between clicks); a back-to-back script shows the
  two-click dropdown highlight and the first agents switch at 217 / 221 ms. Accept, or tighten?
- Gate 6: confirm the `START_PROMPT.md` and `AGENTS.md` edits (Phase 6/7) recorded as approved
  in chat; `START_PROMPT.md` Phase 6 has no "Done when" sentence yet.
- Merge PR (not merged, by instruction).

**Phase 5 (2026-10-24):** the human answered P5-1 to P5-6 (see Decisions); remaining:
none blocking until the LLM baseline report.

<details><summary>Earlier wording of P5-1 to P5-6</summary>


- **P5-1 Model.** The configured model does not support `response_format`/`structured_outputs`
  (OpenRouter public model list), so with `require_parameters: true` no endpoint accepts the
  request. Choose a model that supports structured outputs and approve one more smoke call.
- **P5-2 Disclosure.** Before the smoke call, a test bug (default `env_file` bound at import, so
  a monkeypatch missed it) made one CLI test build a live client from the real `.env`: 36 steps x
  2 attempts = 72 requests of the same shape, all failed (most likely the same 404 routing
  refusal; the error type was not kept). Fixed: `env_file` is read at call time and
  `tests/conftest.py` makes building a live client in any test an error.
- **P5-3** May keyword-search snippets of `policies/extracted/` (non-book PDFs) be sent to
  OpenRouter as context? Default: no (`search_extracted` exists but is off in prompts).
- **P5-5 Repair rules in LLM views** (phase-auditor question). `RoleView.role_clauses` shows a
  replay's hypothetical repair rules from T+00, so LLM agents can adapt to the repair, but those
  views get new cache keys: for the top repair 24 of 36 steps are re-asked (17 differ only by the
  rule). Alternative: hide repair rules (more reuse, agents unaware of the repair). Your choice.
- **P5-6** (test-breaker question) Should `run --repair <id> --agents llm` replay only that
  repair instead of the whole search? For now the CLI refuses any live repair search, like the UI.
- **P5-4** Repair search with LLM agents: about 21 replays and about 312 uncached steps (scripted
  proxy). Run live only on explicit approval; the UI refuses a live repair search until then.

</details>

**2026-10-26 (round 4) question answered by the human:** `invalid_output` steps do not make a
run inconclusive (see Decisions).

**2026-10-25 additions:**
- **Clause review (gate 1):** new draft `uae.fl2-2019.art16-exceptions` — Art 16 items 1-5,
  verbatim, from `UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf`, viewer
  page 5. It completes `uae.fl2-2019.art16` (reviewed, unchanged; its quote stops at "except in
  any of the following cases:" on page 4). No normalized reading (whether item 3 or 5 could
  cover a share is for a human expert).
- **Open question for after Phase 5:** role views do not list open obligations (nor action
  descriptions). Adding them would change every prompt and invalidate the cache, so it is
  deferred (human decision 2026-10-25). In the v2 baseline the notify obligation stayed open.
- **Golden-repair live replay:** the paced rerun (cap 40) completed: 27 requests, 3 HTTP 502
  recovered by backoff, 35/36 replay steps decided (1 invalid_output), verdict **partial** (LLM)
  vs **resolved** (scripted): the operator never proposed reverse_automated_lockouts although
  the ownership rule was in its view. Question: how should repair rules reach LLM agents so
  they act on them? (tied to the open-obligations question)

Answered on 2026-10-24: the Phase 3 items, the spec 004 questions, the section 6 question and
the Phase 4 review gates (see Decisions). Re-approval needed (gate 1): none
(`policies/approvals.yaml`, `reapproval_needed: []`). Still open, none blocking:

1. **Clause review** of the remaining drafts, including 3p: `dha.pp11.4-18-5` takes its actor
   from 4.18.4, outside its quote (the two clauses stay separate).
2. **Sources missing from `policies/sources/`** (optional).
3. **3b:** the human checks the Arabic text of FL 2/2019 ("Health Authority").
   **3i:** the human looks for a complete DHA copy (footers 51/52 and 52/52 missing).

## Known limitations

- **`obligation_overdue` applies to owner obligations only** (human decision 2026-10-26). Other
  missed obligations stay `obligation_missed` / `temporal_infeasibility` (spec 003).
- **Two owners for one action** (test-breaker, unreachable today: needs 3 edits and a changed
  roles file): the opening condition is global ("no role has reversed"), fulfilment is per
  role, so a co-owner's obligation stays open after the other owner acts and goes overdue.

- **Deferred MINORs (round 4):** `DecisionCache._read` checks only the key, not
  `prompt_version`/`model_sha256` inside the file (safe in normal use: both are hashed into the
  key); `Usage.calls` counts agent attempts, not request retries (the clients' own counters are
  exact).

- **Gap-wording false positive (2026-10-25):** the free-text gap pattern matches "no authority"
  when an agent describes its own inaction ("no authority has been triggered ..."), so the
  decision is rejected as `uncited_gap_claim` (v2 LLM baseline, health_data_oversight T+00).
  Not changed (human decision; the pattern stays conservative).
  `test_known_limitation_gap_pattern_flags_own_inaction` pins the behaviour so a fix is
  deliberate.

## Deferred MINOR findings (Phase 1 review)

- `normalized` blocks go beyond the quote in five clauses (see the triage). Settled by
  decision 5h (basis/mapping_note) and open questions h2 and 7p; they are now
  NEEDS-HUMAN-JUDGMENT, not FIX.
- ~~Book filenames as `source_file`; `normalized` names vs `roles.yaml`~~ Done in Phase 2
  (loader rejects book sources, duplicate YAML keys and stray `.yml` files;
  `check_clause_references` runs on every engine run, with tests).
- ~~`RepairProposal` list/dict fields~~ Done in Phase 3: edits and citations are tuples of
  frozen models with typed parameters.
- ~~Deep-freeze and AwareDatetime~~ Done in Phase 2: domain lists are tuples, and `at` and
  `start_time` are `AwareDatetime`. `ProposedAction.parameters` stays a dict; the engine copies
  each decision on receipt and logs only strings.
- Phase 2: `tests/unit/test_scenario.py` validates scenario clause references against all clauses,
  drafts included. Engine runs must use `load_engine_clauses()` or fixtures.

## Next step

The human reviews the Phase 6 PR (branch `phase-6-ui`) and answers the Phase 6 items in
"Waiting on human". Then Phase 7 (tracing, optional). Still open: the deferred MINORs,
the gap-wording known limitation and the two-owners limitation.

Earlier (done):

1. Human, before Phase 5 (LLM agents) can start:
   - put the three variables in `.env` (never committed; names only in `.env.example`):
     `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `CASCADEGUARD_MODEL`;
   - choose the model (`CASCADEGUARD_MODEL`); it is never picked, guessed or defaulted;
   - approve the paid Phase 5 smoke test (gate 4: anything that costs money).
2. Then start Phase 5 on `phase-5-llm`; its first test-breaker round covers a0b6342 and the
   Phase 4 commits after it.
