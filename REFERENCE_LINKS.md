# CascadeGuard Reference Links

Curated tools for this project. Nothing here is a dependency unless `AGENTS.md` lists it.

## GitHub access

- **`git`** for commits, branches, pushes.
- **GitHub CLI (`gh`)** for creating the repo, pull requests, issues, and checking CI.
  Already authenticated on this machine (`gh auth status`). Prefer `gh` over the GitHub MCP.

## MCP servers (configured by the human in `.mcp.json` — the agent does not install or edit them)

`.mcp.json` is committed and contains no secrets. It reads keys from Windows user
environment variables (set once with `setx`): `CONTEXT7_API_KEY`, `GITHUB_PAT`,
`FIRECRAWL_API_KEY`. Restart the terminal/VS Code after changing them.

| MCP | Use it for | Notes |
|---|---|---|
| [Context7](https://github.com/upstash/context7) | Current docs for FastAPI, Pydantic, NiceGUI, DuckDB, NetworkX, Playwright, OpenTelemetry, OpenInference, Phoenix, pytest | Use before writing library code from memory. Highest-value MCP. |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Open the local app, click through incident → replay, inspect UI errors, take screenshots | From Phase 4 onward. Needs Node.js. |
| [GitHub MCP](https://github.com/github/github-mcp-server) | Only if `gh` cannot do the job (e.g. structured PR review comments) | Fine-grained token scoped to the CascadeGuard repo. |
| [Firecrawl MCP](https://github.com/firecrawl/firecrawl-mcp-server) | Only when the human asks to find additional official web sources | Not needed for the 19-PDF knowledge base. Output goes to `policies/sources/web/` — unverified until reviewed. Never use it to parse the local PDFs. |

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
