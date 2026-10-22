# AGENTS.md — CascadeGuard

Durable rules for every coding agent working in this repository (Claude Code, Cline, others).
`CascadeGuard.md` is the authoritative project concept. Read it before any architectural change.

## What we are building

> Find where AI decisions and institutional rules collide, identify the smallest safe repair,
> and replay the same incident to test whether the repair works.

The current target is ONE vertical slice: the `uae_health_access` scenario, end to end.
Breadth (more countries, sectors, agents, policy sources) comes only after that works.

## Architecture boundary (non-negotiable)

**Only the deterministic engine** (`engine/`, `simulation/state.py`) may:
advance scenario state, accept or reject actions, enforce obligations, diagnose failures,
and approve replay outcomes.

**Agents (scripted or LLM)** may only return an `AgentDecision`: proposed actions, rationale,
citations, uncertainty. They must never:

- mutate state directly, or receive a mutable reference to it;
- see information outside their role's boundary at that point in the timeline;
- authorize an action, or override a prohibition or safeguard;
- declare a legal gap without cited evidence and an explicit qualification.

Enforcement in code, not just convention:

- Agents receive a read-only, boundary-filtered view object.
- Every `Citation` must reference a clause ID that exists in `policies/reviewed/`.
  The engine rejects decisions with unknown citation IDs and records that as a finding.
- Repairs must be one of the closed `RepairOperation` types. Free-text repairs are rejected.

## Determinism and replay

- A replay must be the *identical* incident: same timeline, same scenario seed, same agent
  inputs, except where the repair changes them.
- LLM agents run at temperature 0 and go through `agents/cache.py`.
  Cache key = hash(role, boundary-filtered view, prompt version, model id).
  Steps whose inputs are unchanged by the repair must reuse the cached decision.
- The full loop must always run with `ScriptedAgent` and no API key. That is the test
  baseline and the demo fallback.

## Policy and evidence rules

- The policy knowledge base is the set of 19 PDF documents in `policies/sources/`.
  These originals are never modified, renamed, or deleted.
- The engine does not read PDFs. It reads only clause YAML files in `policies/reviewed/`,
  which are extracted from those PDFs.
- Extraction workflow:
  1. `scripts/extract_pdf_text.py` extracts each PDF's text, page by page, into
     `policies/extracted/<pdf-stem>.jsonl` (generated output, kept for search and checking).
  2. The agent drafts YAML clauses only for provisions the scenario actually needs,
     quoting the text verbatim from the extracted page, with `status: draft`.
  3. The human checks each draft against the PDF and changes it to `status: reviewed`.
     Agents never set `status: reviewed` themselves.
- Every clause records: `id`, `title`, `text` (verbatim), `source_file` (PDF filename),
  `page`, `article` (article/section number if present), `issuer`, `jurisdiction`,
  `document_date`, `status` (`draft` | `reviewed` | `illustrative`),
  `binding` (`true` | `false` | `unknown`), plus an optional `normalized` block
  (e.g. obligation type, actor, counterpart, deadline) that the engine checks.
- If a PDF page has no extractable text (scanned image), flag it to the human; do not guess the text.
- Material from Firecrawl or other web scraping goes to `policies/sources/web/`, is unverified,
  and follows the same draft → reviewed process.
- Never present illustrative or unverified material as binding UAE law, in code, UI, or docs.
  The UI must show the `status` label next to any clause it displays.
- Use synthetic data only. No real personal or patient data, ever.

## Technology (decided — do not substitute without asking)

Python 3.12 · uv (commit `uv.lock`) · Pydantic v2 · NiceGUI (UI, runs on FastAPI) ·
NetworkX · DuckDB · pdfplumber (PDF text extraction) · PyYAML · python-dotenv ·
`openai` SDK pointed at OpenRouter (Phase 5) · pytest · Ruff (lint + format) ·
Pyright (type checking) · OpenTelemetry/OpenInference + Phoenix (optional tracing, off by default) ·
Playwright (later).

Graph visualization: NiceGUI `ui.echarts`. No separate React/JS frontend.
Ask before adding any dependency not listed here.

## LLM configuration (Phase 5)

- Provider: OpenRouter, via the `openai` Python SDK with a custom `base_url`.
- Configuration comes only from environment variables loaded from `.env`:
  `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `CASCADEGUARD_MODEL`.
- Never hardcode, guess, or substitute a model ID. If `CASCADEGUARD_MODEL` is missing,
  fail with a clear error message; do not fall back to a default model.
- Never print, log, commit, or copy the contents of `.env`. Maintain `.env.example`
  with variable names only and placeholder values.
- Request structured output validated against `AgentDecision`. If the model returns invalid
  JSON or a schema mismatch, retry once, then record a finding and treat the step as
  "no decision". The engine never repairs or guesses at malformed output.
- Temperature 0. The model ID is part of the cache key, so changing models never reuses
  decisions from another model.
- All roles use the same configured model; roles differ by boundary-filtered view,
  allowed action set, and role instructions (stored in the scenario's `roles.yaml`).

## Working rules

- Work in the current phase only (see `START_PROMPT.md`). Stop and report at the end of each phase.
- Create a module only when the current task needs it. No empty placeholder files.
- Before saying a task is done, run and pass:
  `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest`
- Small, focused commits with clear messages. Never commit `.env`, `data/`, or secrets.
- Keep docs short. Update `docs/architecture.md` when structure changes; add an ADR in
  `docs/decisions/` only for a real decision with trade-offs.
- If a requirement is ambiguous or conflicts with `CascadeGuard.md`, ask. Don't guess silently.
- Use the Context7 MCP for current library docs instead of relying on memory.
- Optional tools in `REFERENCE_LINKS.md` marked "only when asked" stay unused unless the human asks.

## Commands

```bash
uv sync                                              # install
uv run cascadeguard run uae_health_access            # baseline
uv run cascadeguard run uae_health_access --repair <repair-id>   # replay with repair
uv run python -m cascadeguard.ui.app                 # demo UI
uv run pytest                                        # tests
```
