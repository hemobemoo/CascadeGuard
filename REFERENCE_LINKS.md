# CascadeGuard Reference Links

Curated tools for this project. Nothing here is a dependency unless `AGENTS.md` lists it.

## MCP servers (configured by the human before the session — not installed by the agent)

| MCP | Use it for | Notes |
|---|---|---|
| [Context7](https://github.com/upstash/context7) | Current docs for FastAPI, Pydantic, NiceGUI, DuckDB, NetworkX, Playwright, OpenTelemetry, OpenInference, Phoenix, pytest | Check here before writing library code from memory. Highest-value MCP. |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Open the local app, click through incident → replay, inspect UI errors, take screenshots | From Phase 4 onward. |
| [GitHub MCP](https://github.com/github/github-mcp-server) | Issues, pull requests, review, history | Use plain `git` for commits, branches, pushes. |
| [Firecrawl MCP](https://github.com/firecrawl/firecrawl-mcp-server) | Find and extract official UAE, ITU and international policy sources | Needs an API key. Output goes to `policies/sources/` only — unverified until a human reviews it and it is recorded in `policies/reviewed/`. |

## Core libraries (in the stack)

- [NiceGUI](https://github.com/zauberzeug/nicegui) — demo UI (runs on FastAPI; use `ui.echarts` for the graph).
- [DuckDB](https://github.com/duckdb/duckdb) — local audit and results storage.
- [Phoenix](https://github.com/Arize-ai/phoenix) — tracing/evaluation via OpenTelemetry/OpenInference. Not an MCP. Phase 6, optional.

## Process aid

- [GitHub Spec Kit](https://github.com/github/spec-kit) — use lightly: one short spec per phase in `specs/`. Do not run its full multi-step workflow.

## These are optional — use or install them when they are usful and impactful 

- [OpenAPPA](https://github.com/archestra-ai/OpenAPPA) — possible extra guardrail layer, after the constraint engine is stable.
- [Graphify](https://github.com/Graphify-Labs/graphify) — repo/knowledge-graph exploration. The CascadeGuard policy and dependency model stays our own.
- [Agent Skills](https://github.com/addyosmani/agent-skills) — optional engineering guidance.
- [LangChain OpenWiki](https://github.com/langchain-ai/openwiki) — documentation upkeep.
- [Headroom](https://github.com/headroomlabs-ai/headroom) — context/token optimization, only for a measured problem.

## Principles

- Python throughout; no separate frontend unless the Python UI demonstrably cannot do the job.
- MCPs are supporting tools, not product architecture.
- The LLM layer stays separate from the deterministic state, constraint, and replay engine.
- Use official or authoritative sources and keep clause-level provenance.
- Never claim extracted or unverified material is binding UAE law.
