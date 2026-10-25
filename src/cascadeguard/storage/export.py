"""Export runs, repair searches and baseline-vs-replay comparisons as JSON and Markdown.

Every clause id carries its status label (JSON: {"id", "status"}). Repair rules are
hypothetical and say so; every diagnosed failure keeps its qualification (never a confirmed
legal gap).
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from cascadeguard.domain.decisions import GAP_QUALIFICATION
from cascadeguard.domain.findings import CoordinationFailure
from cascadeguard.engine.constraints import CANDIDATE_GAP_CLAIM
from cascadeguard.engine.repair_search import (
    SCRIPTED_LIMIT_NOTE,
    ReplayComparison,
    SearchResult,
    outcome_definition,
)
from cascadeguard.simulation.orchestrator import RunResult

SCRIPTED_NOTE = (
    "Scripted agents replay the same decisions; they do not adapt to the repair. A new "
    "obligation that no scripted decision fulfils shows up as a missed obligation."
)
DISCLAIMER = (
    "Hypothetical scenario with synthetic data only. CascadeGuard is decision support, not legal "
    "interpretation: no output is a legal conclusion or a confirmed legal gap."
)
REPAIR_NOTE = (
    "Repair rules are hypothetical coordination rules for the simulation, not proposals of law. "
    "'requires_authorization': no reviewed, binding clause supports the permission it creates; "
    "it needs human and institutional approval."
)


def _labelled(ids: Iterable[str], labels: dict[str, str]) -> list[dict[str, str]]:
    return [{"id": i, "status": labels.get(i, "not loaded")} for i in ids]


def _label_clause_fields(data: Any, labels: dict[str, str]) -> Any:
    """Replace every "clauses" list and "clause" id in plain data with labelled entries."""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in cast(dict[str, Any], data).items():
            if key == "clauses" and isinstance(value, list):
                out[key] = _labelled((str(v) for v in cast(list[Any], value)), labels)
            elif key == "clause" and isinstance(value, str):
                out[key] = _labelled((value,), labels)[0]
            else:
                out[key] = _label_clause_fields(value, labels)
        return out
    if isinstance(data, list):
        return [_label_clause_fields(v, labels) for v in cast(list[Any], data)]
    return data


def _failure(f: CoordinationFailure, labels: dict[str, str]) -> dict[str, Any]:
    return {
        "id": f.id,
        "category": f.category.value,
        "goals": list(f.goals),
        "roles": list(f.roles),
        "clauses": _labelled(f.clause_ids, labels),
        "description": f.description,
        "qualification": f.qualification,
    }


def run_export(result: RunResult) -> dict[str, Any]:
    labels = dict(result.loaded_clauses)
    data = _label_clause_fields(result.summary(), labels)
    data["failures"] = [_failure(f, labels) for f in result.failures]
    # Findings with their full text: agent statements keep their label, and every candidate gap
    # claim keeps its citations and the fixed qualification.
    data["findings"] = [
        {
            **row,
            "detail": f.detail,
            **({"qualification": GAP_QUALIFICATION} if f.kind == CANDIDATE_GAP_CLAIM else {}),
        }
        for row, f in zip(data["findings"], result.findings, strict=True)
    ]
    data["loaded_clauses"] = _labelled(labels, labels)
    data["agents"] = result.agents
    if result.failed_steps:
        data["failed_steps"] = [
            {"minute": m, "role": r, "reason": why} for m, r, why in result.failed_steps
        ]
    return data


def search_export(result: SearchResult) -> dict[str, Any]:
    labels = dict(result.loaded_clauses)
    data = _label_clause_fields(result.summary(), labels)
    by_id = {c.proposal.repair_id: c for c in result.ranked}
    for row in data["ranked"]:
        c = by_id[row["repair"]]
        row["outcome_definition"] = outcome_definition(c.outcome)
        if c.masked:
            row["masked_note"] = f"{len(c.masked)} masked failures: cause still present"
    return {"clause_set": result.clause_set, "agents": result.agents, "note": REPAIR_NOTE, **data}


def comparison_export(c: ReplayComparison) -> dict[str, Any]:
    labels = dict(c.replay.loaded_clauses)
    by_id = {f.id: f for f in (*c.baseline.failures, *c.replay.failures)}
    data = c.summary()
    for key in ("failures_removed", "failures_masked", "failures_remaining", "new_conflicts"):
        data[key] = [_failure(by_id[fid], labels) for fid in data[key]]
    data["targets_clauses"] = _labelled((x.clause_id for x in c.proposal.citations), labels)
    data["outcome_definition"] = outcome_definition(c.outcome)
    if c.masked:
        data["masked_note"] = f"{len(c.masked)} masked failures: cause still present"
    data["note"] = " ".join(comparison_notes(c))
    data["agents"] = c.replay.agents
    return data


def comparison_notes(c: ReplayComparison) -> tuple[str, ...]:
    """The repair note always; the scripted-agents note only when both runs were scripted."""
    if c.baseline.scripted and c.replay.scripted:
        return (REPAIR_NOTE, SCRIPTED_NOTE)
    return (REPAIR_NOTE,)


def comparison_markdown(c: ReplayComparison) -> str:
    labels = dict(c.replay.loaded_clauses)

    def cite(ids: Iterable[str]) -> str:
        return ", ".join(f"`{i}` [{labels.get(i, 'not loaded')}]" for i in ids) or "none"

    s = c.summary()
    p = c.proposal
    lines = [
        f"# Replay: {p.repair_id}",
        "",
        f"_{DISCLAIMER}_",
        "",
        f"- Scenario: `{s['scenario']}` (synthetic, hypothetical)",
        f"- Clause set: {s['clause_set']}",
        f"- Agents: {c.replay.agents}",
        *(
            [
                "- Steps with no decision (infrastructure): "
                + ", ".join(f"{run} T+{m:02d} {r} ({why})" for run, m, r, why in c.failed_steps)
            ]
            if c.failed_steps
            else []
        ),
        f"- Outcome: **{c.outcome}** ({outcome_definition(c.outcome)})"
        + (f"; {len(c.masked)} masked failures: cause still present" if c.masked else ""),
        "- Requires authorization: "
        + (
            "**yes**: creates a permission with no reviewed, binding basis; needs human and "
            "institutional approval"
            if p.requires_authorization
            else "no"
        ),
        "",
        "## Repair edits (hypothetical rules, not source clauses)",
        "",
    ]
    for e in p.edits:
        params = ", ".join(
            f"{k}={v}" for k, v in e.model_dump(exclude_none=True).items() if k != "operation"
        )
        lines.append(f"- `{e.operation.value}`: {params}")
    lines += ["", f"Clauses the repair targets: {cite(x.clause_id for x in p.citations)}", ""]
    lines += ["## Recovery goals", "", "| Goal | Baseline | Replay |", "|---|---|---|"]
    lines += [f"| {g} | {v['baseline']} | {v['replay']} |" for g, v in s["goals"].items()]
    lines += ["", "## Diagnosed failures", ""]
    by_id = {f.id: f for f in (*c.baseline.failures, *c.replay.failures)}
    for title, ids in (
        ("Removed (the repair removes its cause)", c.removed),
        ("Masked (goal met another way; the cause is still present)", c.masked),
        ("Remaining", c.remaining),
        ("New conflicts introduced by the repair", c.new_conflicts),
    ):
        lines.append(f"**{title}:**" + ("" if ids else " none"))
        tags = c.conflict_tags()
        for fid in ids:
            f = by_id[fid]
            lines.append(f"- `{fid}`: {f.description} Clauses: {cite(f.clause_ids)}.")
            if fid in tags:
                lines.append(f"  Tag `{tags[fid]}`: {SCRIPTED_LIMIT_NOTE}.")
            lines.append(f"  _{f.qualification}_")
        lines.append("")
    lines += ["## Actions whose verdict changed", ""]
    for a in s["changed_actions"]:
        target = f" -> {a['target']}" if "target" in a else ""
        lines.append(
            f"- T+{a['minute']:02d} {a['role']}: {a['action']}{target}: "
            f"{a['baseline']} -> {a['replay']}"
        )
    if not s["changed_actions"]:
        lines.append("none")
    lines += ["", *(f"_{note}_" for note in comparison_notes(c)[1:]), ""]
    return "\n".join(lines)


def write_exports(directory: Path, name: str, data: dict[str, Any], markdown: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{name}.json"
    md_path = directory / f"{name}.md"
    json_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md_path.write_text(markdown, encoding="utf-8")
    return [json_path, md_path]
