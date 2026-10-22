# Spec 001 — Domain, policy extraction, and scenario

## Goal

Give the engine (Phase 2) validated inputs: clauses traceable to PDF pages, and a time-based
scenario whose roles have explicit information boundaries.

## Scope

- `scripts/extract_pdf_text.py`: PDFs → `policies/extracted/<stem>.jsonl` (`source_file`, `page`,
  `text`) plus `_inventory.json` (page count, pages without text, metadata).
- `domain/`: frozen, `extra="forbid"` Pydantic models.
  - `policies.py`: `PolicyClause`, `NormalizedRule`, `ClauseStatus`, `RuleKind`.
  - `decisions.py`: `Citation`, `ProposedAction`, `AgentDecision`.
  - `repairs.py`: `RepairOperationType` (the five from CascadeGuard.md §6), `RepairProposal`.
  - `scenario.py`: `Scenario`, `TimelineEvent`, `Fact`, `Certainty`, `Role`,
    `InformationBoundary`, `Action`, `RoleSet`.
- `knowledge/loader.py`: `load_clauses` (all statuses, for validation), `load_engine_clauses`
  (reviewed + illustrative only), `quote_found_on_page` (verbatim check, `[...]` elisions in order).
- `simulation/loader.py`: `load_scenario` checks that roles, actions and clause ids referenced
  exist, and that each fact's holder can see its category.
- `scenarios/uae_health_access/`: `scenario.yaml`, `roles.yaml`, `README.md`.

## Information model

A **fact** has a data category, a holder and a certainty. A role's **boundary** lists the
categories that may ever reach it. In Phase 2 a fact reaches a role only if it is in the boundary
and the role holds it, received the inject, or was sent it through an action the engine accepted.
A `define_minimum_data_share` repair widens one boundary by one category.

## Acceptance

- Extraction runs over all 19 PDFs. Pages without text are reported, not guessed.
- All clause files load. Every non-illustrative quote is found on its cited page.
- Malformed clauses (missing fields, bad status/date/id, unknown source file, illustrative but
  binding, duplicates, invalid YAML) fail the load.
- The scenario loads with exactly the six institutional roles and no orchestrator role.
- A review list (clause id → PDF → page) is delivered; illustrative rules are listed separately.

## Out of scope

State, boundaries at time *t*, constraints, diagnosis, agents: Phase 2.
