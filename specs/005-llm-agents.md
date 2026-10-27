# 005 — LLM agents (Phase 5)

**Goal.** The six roles can be played by one configured LLM instead of `ScriptedAgent`, with no
change to the engine's authority: an LLM agent returns an `AgentDecision` and nothing else.
Scripted stays the default, the test baseline and the demo fallback, and needs no key.

```bash
uv run cascadeguard run uae_health_access --agents llm             # live calls, cached
uv run cascadeguard run uae_health_access --agents llm --offline   # cache only, no key
uv run python scripts/llm_smoke_test.py                            # exactly one call
```

## Configuration (`agents/llm.py`)

- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `CASCADEGUARD_MODEL` from `.env`
  (python-dotenv). Any missing → `LLMConfigError` naming the variable, never a value. No default
  model. Values are never printed or logged, the model id included (cache files hold its hash).
- `openai` SDK, `base_url` from the env. Request: `temperature=0`; `response_format`
  `{"type": "json_schema", "json_schema": {"name", "strict": true, "schema"}}`;
  `provider: {"require_parameters": true}`; `plugins: [{"id": "response-healing",
  "enabled": false}]` (off even if an account default turns it on, unless the account sets
  "Prevent overrides"). Usage (tokens, `cost`) is read from the response.

**Output mode (human decision 2026-10-24).** `CASCADEGUARD_OUTPUT_MODE` = `json_schema`
(default) | `json_object`, chosen explicitly in `.env`, never switched automatically. In
`json_object` mode the request sends `response_format: {"type": "json_object"}` and the schema
goes into the system prompt; `require_parameters` stays on (JSON-mode endpoints only). Both modes
send `reasoning: {"enabled": false}` and temperature 0. The mode is part of the prompt version
and the cache key, and every run label and export names it.

## Schema

Built from `AgentDecision`: the same fields without `role_id` and `at`, which the agent fills
from its view (the model does not choose its role or the simulation time). Strict mode needs
closed objects, so `parameters` travels as a list of `{name, value}` pairs and becomes the dict.
A test pins the payload's fields to `AgentDecision`'s. The reply is parsed, validated as the
payload, then as a full `AgentDecision`. Invalid JSON or a schema mismatch → one retry → else
the step is "no decision": `AgentDecision.no_decision` is set (closed reason, no model text),
and the engine records a `no_decision` finding. The engine never repairs output.

## Prompt and retrieval (`knowledge/retrieval.py`)

- System: fixed rules (`PROMPT_VERSION`) — propose only, allowed actions only, cite only listed
  clause ids, gaps only as `gap_claims` with the fixed qualification, state uncertainty.
- User: the role's `RoleView` as JSON (instructions, inject if recipient, own decision points,
  boundary-filtered facts, own history) plus `RoleView.role_clauses`: loaded clauses that
  concern the role (the engine's 7n rule over its allowed actions), with text, status label
  and normalized reading. The inject's clauses are listed separately by id and label. Repair rules in a replay appear labelled
  "hypothetical repair rule (not a source clause; not citable)", so an LLM agent can adapt.
  Since prompt v4 (`phase5-v4`, ADR 0002 option A) the view also lists the role's open
  obligations (`your_open_obligations`: id, action, source and its status label, opened_at,
  due_at or "undetermined", open or overdue). Data only; the system prompt is unchanged.
- `search_extracted(query)`: keyword search over `policies/extracted/` (books always excluded),
  "context only, unreviewed, not citable". **Off in prompts by default** (question 1).

## Cache (`agents/cache.py`)

Key = sha256 of canonical JSON {role, view, prompt version, model id, schema}. One JSON file per
key in `data/llm_cache/` (ignored): outcome, decision, tokens, cost, latency. Each step looks up
the cache first; replays therefore reuse every decision whose view the repair did not change.
Invalid-output outcomes are cached (replays stay identical); request errors are kept in
memory for the life of the cache object (a baseline and its replays get the same outcome) but
never written to disk. `--offline`
uses the cache only; a miss is a `no_decision` (`not_cached`). Hits, misses and repeated
request failures are counted per command (the baseline and any replays). A live repair search
(CLI `repairs` / `run --repair`, UI "Find repairs") is refused until approved.

## CLI and UI

`--agents scripted|llm` (default scripted) and `--offline` on `run` and `repairs`. The UI has a
Scripted / LLM (cached only) toggle (Phase 6, human decision 2026-10-26: no live calls from the
  UI; the CLI keeps live runs); every result
shows which agents produced it. LLM text stays under the agent-statement label.

## Tests (no live calls)

Fake client with recorded replies: valid run completes; unknown citation → `unknown_citation`
finding; invalid then valid → one retry; invalid twice → `no_decision` finding; replay hits the
cache for every unchanged view; request body carries the settings above and no healing; missing
env → error without values; offline miss → `no_decision`; scripted path unchanged (goldens).

## Smoke test result (2026-10-24)

One call (health_service_operator, T+15): OpenRouter answered HTTP 404 "No endpoints found that
can handle the requested parameters". OpenRouter's public model list shows the configured model
does not support `response_format` / `structured_outputs`, so `require_parameters` leaves no
endpoint. No tokens, no cost, no decision.

One more call (2026-10-24, human's model, `json_object`): valid AgentDecision, citations
passed the engine, 6.06 s, 2,643 / 619 tokens, cost 0. One capped LLM baseline followed
(PROGRESS.md "Real-model runs").

`--extracted-context` (opt-in, P5-3) adds keyword snippets labelled "context only; not citable".

## Questions for the human

1. May keyword-search snippets from `policies/extracted/` (non-book PDFs) be sent to OpenRouter
   as context? Default: no; only clause YAML text is sent.
2. Repair search with LLM agents replays ~20 candidates; uncached steps cost money. Declined
   for now (P5-4). A single repair may be replayed live (P5-6): `run --repair <id> --agents llm`
   prints the uncached steps from a dry run of the cache and needs `--live`.
3. Choose a model that supports structured outputs (`response_format` json_schema) and
   approve one more smoke call. The settings above stay as specified.

## Added after review (2026-10-25/26)

- Requests: `RetryPolicy` (code defaults, `.env` overrides) drives `ResilientClient`: at most 15
  requests a minute, Retry-After or 5/15/45 s backoff on 429/5xx, at most 3 retries, never
  immediate; a daily-limit 429 raises `DailyLimitReached` (redacted, not chained) and stops the
  run. `CappedClient` sits inside it, so the cap counts every retry; the cap is checked before
  any pacing or backoff wait. Live CLI/UI runs need a cap (`--cap` or `CASCADEGUARD_REQUEST_CAP`).
- Missing steps (`request_failed`, `not_cached`): the outcome is "inconclusive: N steps failed
  for infrastructure reasons"; the comparison withholds goals, failure attributions and changed
  actions in every output; a search lists such replays after the ranked ones
  (`SearchResult.inconclusive`), unranked and without counts.
- An `invalid_output` from a one-attempt run (smoke test) is kept in memory only.
