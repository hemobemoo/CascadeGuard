# Phase 5 report — LLM agents

Branch `phase-5-llm` (not pushed, no PR, not merged, not tagged: waiting for the human).
Spec: `specs/005-llm-agents.md`. Baseline review: `docs/evaluation/llm-baseline-review.md`.

## What was built

- `agents/llm.py`: OpenRouter through the `openai` SDK. Configuration comes only from `.env`,
  with no default model, and errors name the variable, never its value. Settings:
  temperature 0, reasoning off, `provider.require_parameters: true`, response healing
  explicitly disabled. `CASCADEGUARD_OUTPUT_MODE` selects `json_schema` (the default: strict,
  built from `AgentDecision`) or `json_object` (JSON mode, schema in the prompt), chosen
  explicitly and never switched automatically. One retry, then a `no_decision` finding; a
  failed request's finding carries its class, HTTP status and short message (redacted).
- `agents/cache.py`: record/replay. The key covers role, view, prompt version (including the
  output mode), model and schema. A baseline and its replays always get the same outcome for an
  unchanged step. Only a hash of the model id is stored.
- `knowledge/retrieval.py`: the clauses each role may cite, grouped by the proposed action that
  makes them citable (the engine's 7n rule); repair rules shown, labelled hypothetical and not
  citable; opt-in keyword snippets from the non-book extracted PDFs ("context only; not
  citable").
- Engine: `no_decision` finding; `RunResult.agents` in every output and export; screening is
  factored out of the search so a single repair can be replayed (`replay_one`).
- CLI: `--agents scripted|llm`, `--offline`, `--cache`, `--extracted-context`; a live repair
  search is refused; `run --repair <id> --agents llm` replays one repair, printing the
  uncached steps first and requiring `--live`. UI toggle: Scripted / LLM (cached only) /
  LLM (live).
- Scripts: `llm_smoke_test.py` (exactly one call) and `llm_baseline.py` (hard request cap).

## How to run

```bash
uv run cascadeguard run uae_health_access                                  # scripted (default)
uv run cascadeguard run uae_health_access --agents llm --offline           # LLM, from the cache
uv run cascadeguard run uae_health_access --repair <id> --agents llm       # estimate; --live to run
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

Tests: 329 passed (including the e2e browser test). No test can reach a live LLM
(`tests/conftest.py`).

## Real-model runs (model chosen by the human, json_object, total cost 0.000000)

| | v2 baseline | v3 baseline (citations grouped by action) | scripted |
|---|---|---|---|
| Requests (cap 72) | 47 | 37 | – |
| Steps with a decision | 31 / 36 | **36 / 36** | 36 / 36 |
| no_decision findings | 5 | **0** | 0 |
| Rejected citations | 12 (out of scope) | **1** (telecom_operator citing FL Art 4, correctly rejected) | 1 (draft) |
| Free-text gap rejections | 1 (a false positive) | 1 ("no clause authorizes me ...": a free-text absence claim) | 0 |
| Accepted actions | 46 | 62 (9 in common with scripted) | 11 |
| Diagnosed failures | the same 4 | the same 4 | 4 |
| network_incident_reported | T+30 | T+15 | T+45 |
| Health-data oversight notified | no | **yes, T+15** | T+45 |
| Tokens in / out | ~82.9k / ~29.1k | 85.4k / 14.1k | – |

The v2 baseline replays exactly from the cache offline. Smoke call (v2): valid, citations passed,
6.06 s, 2,643 / 619 tokens.

**Single-repair replay (golden successful repair, owner + share):** the dry run reports 25
uncached replay steps (at least 25 requests), which is above the human's limit of 20, so it was
**not run**.

## Reviews

- Round 1 (Phase 4 tail): phase-auditor PASS, test-breaker PASS, evidence-auditor FAIL (2 MINOR
  stale notes, fixed). Triage: `docs/review/phase-5-clause-triage.md`.
- Round 2 (7eaf00b): phase-auditor FAIL (live-run BLOCKER, now resolved by the real-model runs);
  test-breaker FAIL (replay identity on request failures, agent provenance in exports; fixed).
- Round 3 (5192248, last round): test-breaker FAIL (live-search guard read the toggle; fixed).
  Accepted by the human without another round. The review of the real-model run is still to do
  and covers the round-3 fixes first.

## Open for the human

1. The live replay of the golden repair needs 25+ requests: approve a higher limit, or not.
2. P5-4: a live repair search (declined for now).
3. The gap pattern's false positive on "no authority has been triggered" (by design
   conservative; logged, not changed).
4. Possible prompt improvement (not made): list open obligations and action descriptions in the
   view.

Next: the review round on the real-model run, then the PR (do not merge) when approved.
