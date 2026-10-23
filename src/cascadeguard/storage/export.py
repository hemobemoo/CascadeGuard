"""Export a baseline-vs-replay comparison as JSON and Markdown.

Every clause id is printed with its status label. Repair rules are hypothetical and say so;
diagnosed failures keep their qualification (never a confirmed legal gap).
"""

import json
from pathlib import Path
from typing import Any

from cascadeguard.simulation.replay import ReplayComparison

SCRIPTED_NOTE = (
    "Scripted agents replay the same decisions; they do not adapt to the repair. A new "
    "obligation that no scripted decision fulfils shows up as a missed obligation."
)


def comparison_markdown(c: ReplayComparison) -> str:
    labels = dict(c.replay.loaded_clauses)

    def cite(ids: tuple[str, ...] | list[str]) -> str:
        return ", ".join(f"`{i}` [{labels.get(i, 'not loaded')}]" for i in ids) or "none"

    s = c.summary()
    p = c.proposal
    lines = [
        f"# Replay: {p.repair_id}",
        "",
        f"- Scenario: `{s['scenario']}` (synthetic, hypothetical)",
        f"- Clause set: {s['clause_set']}",
        f"- Outcome: **{c.outcome}**",
        "- Requires authorization: "
        + (
            "**yes**: creates a permission with no reviewed basis; needs human and "
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
    lines += ["", f"Clauses the repair targets: {cite([x.clause_id for x in p.citations])}", ""]
    lines += ["## Recovery goals", "", "| Goal | Baseline | Replay |", "|---|---|---|"]
    lines += [f"| {g} | {v['baseline']} | {v['replay']} |" for g, v in s["goals"].items()]
    lines += ["", "## Diagnosed failures", ""]
    by_id = {f.id: f for f in (*c.baseline.failures, *c.replay.failures)}
    for title, ids in (
        ("No longer blocking (the goal it blocked is met, or its cause is gone)", c.removed),
        ("Remaining", c.remaining),
        ("New conflicts introduced by the repair", c.new_conflicts),
    ):
        lines.append(f"**{title}:**" + ("" if ids else " none"))
        for fid in ids:
            f = by_id[fid]
            lines.append(f"- `{fid}`: {f.description} Clauses: {cite(f.clause_ids)}.")
            if fid not in c.removed:
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
    lines += ["", f"_{SCRIPTED_NOTE}_", ""]
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
