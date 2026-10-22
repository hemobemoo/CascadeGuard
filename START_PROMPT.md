# CascadeGuard — Initial Coding-Agent Prompt

You are the primary implementation agent for CascadeGuard, a policy and coordination
failure-testing system for AI-dependent public services.

Before writing any code, read, in this order:

1. `CascadeGuard.md` — the authoritative project concept.
2. `AGENTS.md` — durable rules: architecture boundary, repair grammar and ranking, determinism,
   evidence, git workflow, tooling, working rules.
3. `cascadeguard_project_structure.txt` — target layout and the phase in which each part appears.
4. `REFERENCE_LINKS.md` — which external tools to use, and which to leave alone.

Then reply with a short summary of your understanding and any conflicts or open questions
before starting Phase 0. Create `PROGRESS.md` (see `AGENTS.md`) as part of Phase 0.

Preserve the central idea:

> Find where AI decisions and institutional rules collide, identify the smallest safe repair,
> and replay the same incident to test whether the repair works.

## Objective: one convincing vertical slice

For the `uae_health_access` scenario only:

1. Load a structured, time-based incident scenario.
2. Apply separate information boundaries to institutional roles.
3. Produce proposed role decisions.
4. Validate those proposals with the deterministic constraint engine.
5. Identify a cross-agency coordination failure.
6. Generate repairs from the closed repair grammar.
7. Replay the identical incident with the selected repair.
8. Display and export the baseline-versus-replay comparison.

Do not implement other countries, sectors, agents, policy sources, or the three controlled
variants yet.

## Key decision: deterministic first, LLM last

Build and test the whole loop with `ScriptedAgent` (decisions read from scenario YAML) before
any LLM is involved. The LLM agent is a drop-in replacement behind the same `Agent` protocol
and is added in Phase 5. The scripted path must keep working forever: it is the test baseline
and the live-demo fallback.

## Core contracts (starting point — refine in Phase 1, keep the shape)

```python
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field


class Citation(BaseModel):
    clause_id: str                      # must exist in policies/reviewed/
    quote_span: str | None = None       # short excerpt, optional
    relevance: str                      # why this clause supports the action


class ProposedAction(BaseModel):
    action_type: str                    # from the scenario's allowed action set
    target: str | None = None           # role, system, or data object acted on
    parameters: dict[str, str] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    role_id: str
    at: datetime                        # simulation time, not wall-clock
    proposed_actions: list[ProposedAction]
    rationale: str
    citations: list[Citation]
    uncertainty: list[str]


class RepairOperationType(StrEnum):
    # The fixed repair grammar from CascadeGuard.md §6. Do not add types without asking.
    ASSIGN_OWNER = "assign_owner"
    ADD_ESCALATION_TRIGGER = "add_escalation_trigger"
    DEFINE_MINIMUM_DATA_SHARE = "define_minimum_data_share"
    ADD_FALLBACK_CHANNEL = "add_fallback_channel"
    DESIGNATE_DECISION_REQUESTER = "designate_decision_requester"


class RepairProposal(BaseModel):
    repair_id: str
    operation: RepairOperationType
    applies_to: list[str]               # role ids / clause ids / graph edges affected
    parameters: dict[str, str] = Field(default_factory=dict)
    rationale: str
    citations: list[Citation]
    requires_authorization: bool = False  # True if it creates a permission with no reviewed basis
```

"Smallest safe repair" ranking (engine, deterministic, lexicographic, per `CascadeGuard.md` §6
and `AGENTS.md`): first discard any repair that permits a prohibited action or violates a
safeguard; then most critical blockers removed; then fewest repair edits; then tie-breaks
(no authorization needed first, fewest roles and clauses touched, `repair_id`).

## Phases — stop and report after each one

Each report: what was built, how to run it, test results, open questions, and what the next
phase will do. Deliver it as the PR description (see the git workflow in `AGENTS.md`).
Wait for approval before continuing.

**Phase 0 — Tooling.** `uv` project on Python 3.12, Ruff, Pyright, pytest, `.gitignore`
(including the two published books and their extracted text), `.env.example` with the
`AGENTS.md` variable names, package skeleton with `cli.py` stub, `README.md`, `PROGRESS.md`.
Done when all checks pass on an empty test.

**Phase 1 — Domain, policy extraction, and scenario.**

1a. *Inventory.* List the 19 PDFs in `policies/sources/` with title, issuer, date,
page count, and whether text extracts cleanly. Report scanned or unreadable pages.

1b. *Extraction.* `scripts/extract_pdf_text.py` (pdfplumber) writes page-by-page text to
`policies/extracted/<pdf-stem>.jsonl` (`source_file`, `page`, `text`). Do not edit the PDFs.

1c. *Domain.* Pydantic models in `domain/`, including `PolicyClause` with the fields in
`AGENTS.md`. Reviewed-clause loader that rejects malformed clauses and loads only
`status: reviewed` or `status: illustrative` clauses into the engine.

1d. *Scenario.* `scenarios/uae_health_access/` with `scenario.yaml`, `roles.yaml`
(the six institutional roles from `CascadeGuard.md` §5, their information boundaries,
allowed actions and role instructions; the Orchestrator is code, not a role here), and
`README.md`. Determine the applicable health-data regime from the sources rather than
assuming Federal Decree-Law No. 45 of 2021 applies (see `CascadeGuard.md` §7).

1e. *Clause drafts.* Draft YAML clauses in `policies/reviewed/` only for the provisions the
scenario needs, quoting text verbatim from the extracted pages, with `source_file`, `page`,
and `article`, and `status: draft`. Then STOP and give me a review list
(clause id → PDF → page) so I can verify each one and mark it `reviewed`.
Any rule the scenario needs that no PDF supports must be labelled `illustrative`,
and listed separately in your report.

Write `specs/001-domain-and-scenario.md`. Done when extraction runs, the scenario and
clauses load and validate in tests, and the review list has been delivered.

**Phase 2 — Engine with scripted agents.** `simulation/state.py`, `boundaries.py`,
`orchestrator.py`; `engine/constraints.py`, `graph.py`, `diagnosis.py`; `agents/base.py`,
`scripted.py`; `scripted_decisions.yaml`; `expected_baseline.yaml`.
`uv run cascadeguard run uae_health_access` prints the timeline, accepted/rejected actions,
and the diagnosed coordination failure. Done when an integration test proves the baseline
failure reproduces exactly as in `expected_baseline.yaml`, and a test proves an agent cannot
see data outside its boundary.

**Phase 3 — Repair and replay.** `engine/repair_search.py`, `simulation/replay.py`,
`storage/audit.py` (DuckDB). `--repair <id>` replays the identical incident and prints a
baseline-vs-replay comparison; export to JSON and Markdown. Done when golden tests cover
baseline and at least one successful and one unsuccessful repair (for example, a repair
that clears the information deadlock but leaves the lockout unresolved).

**Phase 4 — Demo UI.** NiceGUI: scenario picker, timeline, dependency graph (`ui.echarts`)
with the failure highlighted, repair list, side-by-side replay, export button, clause status
labels visible. Done when the full flow works in the browser using scripted agents.

**Phase 5 — LLM agents.** `agents/llm.py` and `agents/cache.py`, `knowledge/retrieval.py`.

- Use the `openai` SDK with OpenRouter as configured in `AGENTS.md`
  (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `CASCADEGUARD_MODEL` from `.env`).
  I choose the model; do not pick or hardcode one.
- Each role is the same model with a different boundary-filtered view, allowed action set,
  and role instructions from `roles.yaml`. Agents are code in this repository, not separate
  models and not Claude Code subagents or commands.
- Retrieval: give each agent the reviewed clauses relevant to its role, plus optional
  keyword search over `policies/extracted/` for context. Agents may cite only reviewed or
  illustrative clause IDs.
- Structured output validated against `AgentDecision`; one retry on invalid output, then a
  finding. Temperature 0; record/replay cache. A CLI/UI toggle switches scripted ↔ LLM.
- Start with a single smoke-test call and report cost and latency before running full scenarios.

Done when an LLM run completes, unknown citations are rejected as findings, and a replay
reuses cached decisions for unchanged steps.

**Phase 6 — Tracing (optional).** OpenTelemetry/OpenInference to Phoenix for retrieval,
agent decisions, constraint checks, and replay. Off by default; enabled by an env flag.

## Definition of done for the slice

- `uv run cascadeguard run uae_health_access` reproduces the baseline failure.
- `uv run cascadeguard run uae_health_access --repair <id>` shows whether the repair fixes it.
- The same flow works in the NiceGUI demo, with scripted agents and with LLM agents.
- All checks in `AGENTS.md` pass. No clause is shown without its status label.

## If something is unclear

Ask. Don't fill gaps by inventing scope, legal claims, or new dependencies.
