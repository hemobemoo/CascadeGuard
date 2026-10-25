"""Display rows for the demo UI: formatting only, no decisions.

Everything here comes from engine results (`RunResult`, `SearchResult`, `ReplayComparison`).
Labels come from the engine and `storage/export.py`: clause status labels, the hypothetical
repair-rule label, masked blockers, `scripted_agent_limit` tags and the agent-statement label.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from cascadeguard.cli import baseline_markdown, excluded_drafts, search_markdown
from cascadeguard.domain.scenario import Scenario
from cascadeguard.engine.constraints import AGENT_STATEMENT
from cascadeguard.engine.repair_search import (
    INCONCLUSIVE_LISTED,
    MASKED_LABEL,
    REMOVED_LABEL,
    REQUIRES_AUTHORIZATION_LABEL,
    SCRIPTED_LIMIT_NOTE,
    ReplayComparison,
    SearchResult,
    outcome_text,
)
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.simulation.replay import REPAIR_LABEL
from cascadeguard.storage.export import (
    DISCLAIMER as DISCLAIMER,
)
from cascadeguard.storage.export import (
    REPAIR_NOTE,
    comparison_export,
    comparison_markdown,
    comparison_notes,
    run_export,
    search_export,
)

MASKED = MASKED_LABEL
REQUIRES_AUTHORIZATION = REQUIRES_AUTHORIZATION_LABEL
UNLABELLED = "<unlabelled agent text withheld>"


def cite(ids: Iterable[str], labels: dict[str, str]) -> str:
    """Clause ids, each with its status label (or "not loaded")."""
    return ", ".join(f"{c} [{labels.get(c, 'not loaded')}]" for c in ids)


def clause_set(result: RunResult, corpus_ids: frozenset[str]) -> list[str]:
    """Loaded clauses with their status labels, then how many drafts were left out."""
    loaded = [f"{cid} [{label}]" for cid, label in result.loaded_clauses]
    drafts = len(corpus_ids - {cid for cid, _ in result.loaded_clauses})
    note = (
        f"{drafts} draft clauses not loaded (awaiting human review); decisions citing them are "
        "rejected"
    )
    return [*loaded, note] if drafts else loaded


@dataclass(frozen=True, slots=True)
class InjectRow:
    minute: int
    title: str
    recipients: tuple[str, ...]
    lines: tuple[str, ...]  # actions, obligations and goals at this minute, labelled


def timeline(result: RunResult, scenario: Scenario) -> list[InjectRow]:
    labels = dict(result.loaded_clauses)
    rows: list[InjectRow] = []
    for event in scenario.events:
        lines: list[str] = []
        for e in result.log:
            if e.minute != event.at_minute:
                continue
            cites = f"  {{{cite(e.clause_ids, labels)}}}" if e.clause_ids else ""
            if e.kind in ("accepted", "rejected"):
                what = e.action or "whole decision"
                target = f" -> {e.target}" if e.target else ""
                why = f"  ({', '.join(e.reasons)})" if e.reasons else ""
                detail = f"  {e.detail}" if e.detail else ""
                lines.append(f"{e.kind.upper()} {e.role}: {what}{target}{why}{cites}{detail}")
            elif e.kind.startswith("obligation_"):
                note = f" ({e.detail})" if e.detail else ""
                lines.append(f"{e.kind} {e.role}: {e.action}{note}{cites}")
            elif e.kind == "goal_met":
                lines.append(f"goal met: {e.detail}")
        rows.append(InjectRow(event.at_minute, event.title, event.recipients, tuple(lines)))
    return rows


@dataclass(frozen=True, slots=True)
class RoleViewRows:
    role: str
    minute: int
    recipient: bool
    at: str
    title: str
    description: str
    instructions: str
    allowed_actions: tuple[str, ...]
    decision_points: tuple[str, ...]
    facts: tuple[str, ...]
    clauses: tuple[str, ...]
    role_clauses: tuple[str, ...]  # with labels; repair rules marked not citable
    own_history: tuple[str, ...]
    inside: tuple[str, ...]  # data categories inside the role's boundary
    outside: tuple[str, ...]
    agent_statements: tuple[str, ...]  # always under the AGENT_STATEMENT label


def role_view(result: RunResult, role: str, minute: int, categories: Iterable[str]) -> RoleViewRows:
    """Exactly the view the role's agent received at this inject, plus its boundary within
    every scenario data category (`categories`) and its own labelled agent statements."""
    view = next(v for v in result.views if v.role_id == role and v.minute == minute)
    inside = dict(result.boundaries)[role]
    # Only this role's own decision entries. The engine always labels agent text; an unlabelled
    # entry (a regression) is shown as a placeholder, never as text and never dropped silently.
    statements = tuple(
        e.detail if e.detail.startswith(AGENT_STATEMENT) else UNLABELLED
        for e in result.log
        if e.kind == "decision" and e.role == role and e.minute == minute
    )
    return RoleViewRows(
        role=role,
        minute=minute,
        recipient=view.event_id is not None,
        at=view.at.isoformat(),
        title=view.event_title,
        description=view.event_description,
        instructions=view.instructions,
        allowed_actions=view.allowed_actions,
        decision_points=view.decision_points,
        facts=tuple(
            f"{f.id} ({f.data_category}, {f.certainty.value}): {f.statement}" for f in view.facts
        ),
        clauses=tuple(f"{c.id} [{c.status_label}]: {c.title}" for c in view.clauses),
        role_clauses=tuple(f"{c.id} [{c.status_label}]: {c.title}" for c in view.role_clauses),
        own_history=view.own_history,
        inside=inside,
        outside=tuple(c for c in sorted(set(categories)) if c not in inside),
        agent_statements=statements,
    )


@dataclass(frozen=True, slots=True)
class FailureRow:
    id: str
    category: str
    description: str
    clauses: str
    blocks: str
    qualification: str


def failures(result: RunResult) -> list[FailureRow]:
    labels = dict(result.loaded_clauses)
    return [
        FailureRow(
            f.id,
            f.category.value,
            f.description,
            cite(f.clause_ids, labels) or "none found in the loaded clause set",
            ", ".join(f.goals),
            f.qualification,
        )
        for f in result.failures
    ]


def findings(result: RunResult) -> list[str]:
    """Engine findings. Agent text in them is already labelled; gap claims carry their
    citations and the fixed qualification."""
    labels = dict(result.loaded_clauses)
    return [
        f"T+{f.minute:02d} {f.kind}: {f.detail}"
        + (f"  {{{cite(f.clause_ids, labels)}}}" if f.clause_ids else "")
        for f in result.findings
    ]


def _failure_nodes(result: RunResult, failure_id: str) -> tuple[set[str], set[str]]:
    """(every node the failure names, its subject nodes: the action, or the category and role
    of an information deadlock)."""
    f = next(x for x in result.failures if x.id == failure_id)
    if "->" in f.subject:  # information deadlock: "<category>-><role>"
        category, role = f.subject.split("->")
        subject = {f"category:{category}", f"role:{role}"}
    else:
        subject = {f"action:{f.subject}"}
    nodes = {f"role:{r}" for r in f.roles} | {f"clause:{c}" for c in f.clause_ids}
    nodes |= {f"goal:{g}" for g in f.goals} | subject
    return nodes, subject


KINDS = ("role", "action", "category", "clause", "goal")


def graph_option(result: RunResult, failure_id: str | None = None) -> dict[str, Any]:
    """ECharts option for the dependency graph. Nodes named by the selected diagnosed failure (or
    by every failure when none is selected) are highlighted, and so are the edges between them
    that touch the failure's subject."""
    edges = result.graph.edges()
    names = sorted({n for s, _, t in edges for n in (s, t)})
    ids = [failure_id] if failure_id else [f.id for f in result.failures]
    hot: set[str] = set()
    hot_edges: set[tuple[str, str]] = set()
    for i in ids:
        nodes, subject = _failure_nodes(result, i)
        hot |= nodes
        hot_edges |= {(s, t) for s, _, t in edges if s in nodes and t in nodes and {s, t} & subject}
    labels = dict(result.loaded_clauses)

    def label(n: str) -> str:
        kind, ident = n.split(":", 1)
        return f"{ident} [{labels.get(ident, 'not loaded')}]" if kind == "clause" else ident

    nodes = [
        {
            "id": n,
            "name": label(n),
            "category": KINDS.index(n.split(":", 1)[0]),
            "symbolSize": 26 if n in hot else 12,
            "itemStyle": {"borderColor": "#c62828", "borderWidth": 4} if n in hot else {},
            "label": {"show": n in hot or n.startswith("role:"), "color": "#1f2937"},
        }
        for n in names
    ]
    links = [
        {
            "source": s,
            "target": t,
            "value": rel,
            "lineStyle": {"color": "#c62828", "width": 3, "opacity": 0.9}
            if (s, t) in hot_edges
            else {"opacity": 0.25},
        }
        for s, rel, t in edges
    ]
    return {
        "tooltip": {},
        "legend": [{"data": list(KINDS)}],
        "series": [
            {
                "type": "graph",
                "layout": "force",
                "roam": True,
                "draggable": True,
                "force": {"repulsion": 160, "edgeLength": 70},
                "categories": [{"name": k} for k in KINDS],
                "edgeSymbol": ["none", "arrow"],
                "data": nodes,
                "links": links,
            }
        ],
    }


@dataclass(frozen=True, slots=True)
class RepairRow:
    rank: int
    repair_id: str
    outcome: str
    edits: int
    removed: int
    masked: tuple[str, ...]
    new_conflicts: tuple[str, ...]  # each with its tag and explanation, if any
    authorization: str


def repairs(result: SearchResult) -> list[RepairRow]:
    rows: list[RepairRow] = []
    for i, c in enumerate(result.ranked, 1):
        tags = c.conflict_tags()
        rows.append(
            RepairRow(
                rank=i,
                repair_id=c.proposal.repair_id,
                outcome=outcome_text(c),
                edits=len(c.proposal.edits),
                removed=c.critical_blockers_removed,
                masked=tuple(f"{f}: {MASKED}" for f in c.masked),
                new_conflicts=tuple(
                    f"{f} [{tags[f]}: {SCRIPTED_LIMIT_NOTE}]" if f in tags else f
                    for f in c.new_conflicts
                ),
                authorization=REQUIRES_AUTHORIZATION if c.proposal.requires_authorization else "",
            )
        )
    return rows


def inconclusive(result: SearchResult) -> list[tuple[str, str]]:
    """(repair id, status) of replays listed after the ranked ones: unranked, no counts."""
    return [
        (c.proposal.repair_id, INCONCLUSIVE_LISTED.format(n=len(c.failed_steps)))
        for c in result.inconclusive
    ]


def incomplete_banner(failed: tuple[tuple[int, str, str], ...], run: str = "") -> str:
    """The UI banner for a run with steps that had no decision (as the CLI and Markdown)."""
    if not failed:
        return ""
    where = f"{run} " if run else ""
    steps = ", ".join(f"T+{m:02d} {r} ({why})" for m, r, why in failed)
    return f"Incomplete run: {len(failed)} {where}steps had no decision: {steps}"


def discarded(result: SearchResult) -> list[str]:
    labels = dict(result.loaded_clauses)
    return [f"{d.repair_id}: {d.reason}: {cite(d.clause_ids, labels)}" for d in result.discarded]


@dataclass(frozen=True, slots=True)
class Comparison:
    repair_id: str
    outcome: str
    authorization: str
    edits: tuple[str, ...]  # each labelled as a hypothetical repair rule
    targets: str
    goals: tuple[tuple[str, str, str], ...]  # (goal, baseline, replay)
    baseline_failures: tuple[str, ...]
    replay_failures: tuple[str, ...]  # remaining, masked and new, each marked
    removed: tuple[str, ...]
    changed_actions: tuple[str, ...]
    notes: tuple[str, ...] = field(default=(REPAIR_NOTE,))
    incomplete: str = ""  # an "Incomplete run" banner when steps had no decision
    withheld: str = ""  # set when the replay is not comparable (verdicts withheld)


def comparison(c: ReplayComparison) -> Comparison:
    labels = dict(c.replay.loaded_clauses)
    s = c.summary()
    if c.failed_steps:  # not comparable: no goals, failure attributions or changed actions
        p = c.proposal
        return Comparison(
            repair_id=p.repair_id,
            outcome=outcome_text(c),
            authorization=REQUIRES_AUTHORIZATION if p.requires_authorization else "",
            edits=tuple(f"{e.operation.value} ({e.edit_id}) [{REPAIR_LABEL}]" for e in p.edits),
            targets=cite((x.clause_id for x in p.citations), labels) or "none",
            goals=(),
            baseline_failures=(),
            replay_failures=(),
            removed=(),
            changed_actions=(),
            notes=comparison_notes(c),
            incomplete=incomplete_banner(
                tuple((m, f"{r} ({run})", why) for run, m, r, why in c.failed_steps), ""
            ),
            withheld=str(s["withheld"]),
        )
    tags = c.conflict_tags()
    p = c.proposal
    replay_rows = [f"{f}: remaining" for f in c.remaining]
    replay_rows += [f"{f}: {MASKED}" for f in c.masked]
    replay_rows += [
        f"{f}: NEW conflict" + (f" [{tags[f]}: {SCRIPTED_LIMIT_NOTE}]" if f in tags else "")
        for f in c.new_conflicts
    ]
    return Comparison(
        repair_id=p.repair_id,
        outcome=outcome_text(c),
        authorization=REQUIRES_AUTHORIZATION if p.requires_authorization else "",
        edits=tuple(f"{e.operation.value} ({e.edit_id}) [{REPAIR_LABEL}]" for e in p.edits),
        targets=cite((x.clause_id for x in p.citations), labels) or "none",
        goals=tuple((g, v["baseline"], v["replay"]) for g, v in s["goals"].items()),
        baseline_failures=tuple(f.id for f in c.baseline.failures),
        replay_failures=tuple(replay_rows),
        removed=tuple(f"{f}: {REMOVED_LABEL}" for f in c.removed),
        changed_actions=tuple(
            f"T+{a['minute']:02d} {a['role']}: {a['action']}"
            + (f" -> {a['target']}" if "target" in a else "")
            + f": {a['baseline']} -> {a['replay']}"
            for a in s["changed_actions"]
        ),
        notes=comparison_notes(c),
        incomplete=incomplete_banner(
            tuple((m, f"{r} ({run})", why) for run, m, r, why in c.failed_steps), ""
        ),
    )


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@dataclass(frozen=True, slots=True)
class ExportFile:
    label: str  # button text
    filename: str
    content: str


def export_files(
    scenario_id: str,
    baseline: RunResult,
    search_result: SearchResult | None = None,
    selected: ReplayComparison | None = None,
) -> list[ExportFile]:
    """The same JSON and Markdown as the CLI --export, as browser downloads."""
    files = [
        ExportFile("Baseline JSON", f"{scenario_id}-baseline.json", _json(run_export(baseline))),
        ExportFile(
            "Baseline Markdown",
            f"{scenario_id}-baseline.md",
            baseline_markdown(scenario_id, baseline, excluded_drafts(baseline)),
        ),
    ]
    if search_result is not None:
        files += [
            ExportFile(
                "Repairs JSON", f"{scenario_id}-repairs.json", _json(search_export(search_result))
            ),
            ExportFile(
                "Repairs Markdown",
                f"{scenario_id}-repairs.md",
                search_markdown(scenario_id, search_result),
            ),
        ]
    if selected is not None:
        name = f"{scenario_id}-replay-{selected.proposal.repair_id}"
        files += [
            ExportFile("Replay JSON", f"{name}.json", _json(comparison_export(selected))),
            ExportFile("Replay Markdown", f"{name}.md", comparison_markdown(selected)),
        ]
    return files
