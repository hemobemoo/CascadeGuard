# Phase 5 report — LLM agents

Branch `phase-5-llm`, PR #6 (open; not merged, not tagged: waiting for the human).
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
- Scripts: `llm_smoke_test.py` (exactly one call), `llm_baseline.py` and `llm_replay.py`
  (hard request cap, retries included). Live CLI/UI runs need a cap too (`--cap` or
  `CASCADEGUARD_REQUEST_CAP`).

## How to run

```bash
uv run cascadeguard run uae_health_access                                  # scripted (default)
uv run cascadeguard run uae_health_access --agents llm --offline           # LLM, from the cache
uv run cascadeguard run uae_health_access --repair <id> --agents llm       # estimate; --live to run
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

Tests: all pass (including the e2e browser test; count in the PR). No test can reach a live LLM
(`tests/conftest.py`).

## Real-model runs (model chosen by the human, json_object, total cost 0.000000)

| | v2 baseline | v3 baseline (citations grouped by action) | scripted |
|---|---|---|---|
| Requests (cap 72) | 47 | 37 | – |
| Steps with a decision | 31 / 36 | **36 / 36** | 36 / 36 |
| no_decision findings | 5 | **0** | 0 |
| Rejected citations | 12 (out of scope) | **1** (telecom_operator citing FL Art 4, correctly rejected) | 1 (draft) |
| Free-text gap rejections | 1 (a false positive) | 1 ("no clause authorizes me ...": a free-text absence claim) | 0 |
| Accepted actions, distinct (minute, role, action) | 46 (47 entries) | 62 (9 in common with scripted) | 11 |
| Diagnosed failures | the same 4 | the same 4 | 4 |
| network_incident_reported | T+30 | T+15 | T+45 |
| Health-data oversight notified | no | **yes, T+15** | T+45 |
| Tokens in / out | ~82.9k / ~29.1k | 85.4k / 14.1k | – |

At the time (prompt v2), the v2 baseline replayed exactly from the cache offline; current
code (prompt v3) no longer selects v2 entries. Smoke call (v2): valid, citations passed,
6.06 s, 2,643 / 619 tokens.

**Engine catching an LLM reasoning error (example).** `dha.pp11.4-18-1` obliges the operator
to *maintain* a fallback plan; human decision h2 says it gives no authority to *activate* one.
In the v2 baseline (T+60) the health operator cited 4.18.1 as supporting the activation of a
fallback channel and proposed `activate_fallback_channel`; in v3 it again proposed it with 4.18.1
among the citations (T+15, T+60, T+75). The engine rejected each
proposal as `authority_uncertain`, and the orphan-duty failure for activate_fallback_channel
stayed diagnosed. The agent misread the clause; the deterministic rule held.

**Paced single-repair replay (golden repair; approved, cap 40; 2026-10-25) — complete:**
- 36/36 baseline steps and 14 replay steps from the cache (3 of the 4 previously cached replay
  steps were reused; the 4th, T+30 policy_legal_adviser, had a changed view), 22 live.
- 27 requests: 3 request retries after HTTP 502 (each recovered by one 15 s backoff), 2
  invalid-output retries; no request failed, no 429. Wall clock 344 s; cost 0.000000;
  65.3k / 10.6k tokens.
- 35 of 36 replay steps decided; telecom_operator T+15 returned invalid output twice
  (`invalid_output`, a model failure, not infrastructure), so the verdict is not inconclusive.
- Result vs scripted: LLM **partial**, scripted **resolved**. Both remove the information
  deadlock and the reverse_automated_lockouts orphan duty; no new conflicts in either.
  alert_cause_known_to_health is met at T+30 in both. patient_access_restored stays unmet in the
  LLM replay (scripted: T+60), and activate_fallback_channel and review_automated_lockouts
  remain (scripted: masked). network_incident_reported: LLM T+30, scripted T+45.
- Why: the health operator received the network status (T+30) but never proposed
  reverse_automated_lockouts. At T+45 it listed "who owns reviewing and reversing automated
  lockouts within my remit" as unknown, although the repair rule naming it the owner was in its
  view (as a non-citable hypothetical rule). The ownership rule gives authority but opens no
  obligation, and the view lists no open obligations (the deferred question). A finding about
  how LLM agents take up repairs, not a defect in the engine.
- Export: `data/llm_replay_paced/` (rebuilt offline from the cache with current code: 72 steps
  reused, the same decisions; re-exported after the round-4 display fixes).

**Earlier single-repair live replay (cap 50, unpaced):** inconclusive because of provider
failures.
- Dry run before any call: baseline fully cached; 25 of 36 replay steps change; the first
  changed step is #0 (T+00 health_service_operator). Repair rules are shown from T+00 to the
  roles they concern (P5-5), so no replay step precedes the change. The baseline came 36/36 from
  the cache, and the 11 unchanged replay steps were cache hits.
- 25 live steps, 47 requests (22 retries), cost 0.000000, 10.7k / 0.8k tokens. Only 4 live
  steps produced a decision; 21 ended `request_failed`: first HTTP 502 ("Provider returned
  error"), then HTTP 429 ("Rate limit exceeded: free-models-per-min", the free tier's 20
  requests a minute).
- Against the scripted replay of the same repair: both remove the information deadlock and the
  reverse_automated_lockouts orphan duty. The scripted replay resolves (patient_access_restored
  at T+60; the other two failures masked). The LLM replay leaves activate_fallback_channel and
  review_automated_lockouts remaining, misses patient_access_restored, and shows a new conflict
  (telecom report missed). That conflict comes from the telecom operator's failed steps, not
  from the repair, so the comparison does not measure the repair. A meaningful replay needs
  pacing under the rate limit (or a paid endpoint) and a new approval.
- Found by this run and fixed: OpenRouter's error body carries response headers in `metadata`,
  and they reached the finding text (in memory and the console only; nothing in the repository).
  Error details now keep only the body's `message`, cut before any `headers` key (test added).

## Finding: an LLM agent did not take up a repair's ownership duty (ADR 0002, option C)

In the paced replay of the golden repair, the health operator never proposed
reverse_automated_lockouts, so the LLM replay is **partial** where the scripted replay is
**resolved**. This is **possibly caused by how repairs are shown to agents**: the ownership rule
appears only as a non-citable hypothetical rule, and it opens no obligation that the view would
list. It is **not a confirmed policy gap**, and it says nothing about the source law. Option A
(the owner repair opens an obligation; views list open obligations) is the first task after
Phase 5 (ADR 0002).

## Reviews

- Round 1 (Phase 4 tail): phase-auditor PASS, test-breaker PASS, evidence-auditor FAIL (2 MINOR
  stale notes, fixed). Triage: `docs/review/phase-5-clause-triage.md`.
- Round 2 (7eaf00b): phase-auditor FAIL (live-run BLOCKER, now resolved by the real-model runs);
  test-breaker FAIL (replay identity on request failures, agent provenance in exports; fixed).
- Round 3 (5192248, last round): test-breaker FAIL (live-search guard read the toggle; fixed).
  Accepted by the human without another round. The review of the real-model run is still to do
  and covers the round-3 fixes first.

## Open for the human

1. How should repair rules reach LLM agents so they act on them (e.g. an ownership rule as an
   open duty in the view)? Related to item 4; changes every prompt.
2. P5-4: a live repair search (declined for now).
3. Known limitation: the gap pattern's false positive on "no authority has been triggered"
   (pinned by a test; not changed).
4. After Phase 5: list open obligations (and action descriptions) in the role views. Not done
   now: it changes every prompt and invalidates the cache.
5. Clause review: `uae.fl2-2019.art16-exceptions` (draft; FL 2/2019 PDF, page 5).

Next: the human merges PR #6 and tags `phase-5`; then ADR 0002 option A.
