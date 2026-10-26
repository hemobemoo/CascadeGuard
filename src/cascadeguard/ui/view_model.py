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
from cascadeguard.domain.findings import FailureCategory
from cascadeguard.domain.repairs import OWNER_RULE_PREFIX
from cascadeguard.domain.scenario import Scenario
from cascadeguard.engine.constraints import AGENT_STATEMENT, OBLIGATION_OVERDUE
from cascadeguard.engine.repair_search import (
    INCONCLUSIVE_LISTED,
    MASKED_LABEL,
    OPEN_AT_END_LABEL,
    OVERDUE_LABEL,
    REMOVED_LABEL,
    REQUIRES_AUTHORIZATION_LABEL,
    SCRIPTED_LIMIT_NOTE,
    ReplayComparison,
    SearchResult,
    outcome_text,
)
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.simulation.replay import REPAIR_LABEL
from cascadeguard.simulation.state import ObligationStatus
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
    open_obligations: tuple[str, ...]  # with the source's status label and deadline
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
        open_obligations=tuple(
            f"{o.action} ({o.status}): opened T+{o.opened_at:02d}, due "
            + ("undetermined" if o.due_at is None else f"T+{o.due_at:02d}")
            + f"; {o.source} [{o.source_label}]"
            for o in view.open_obligations
        ),
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

    # Fixed layered layout, one column per kind (roles -> actions -> categories -> clauses ->
    # goals): the same positions for every highlight, so an update only restyles (no force
    # simulation in the browser; spec 006 click budget).
    columns: dict[str, list[str]] = {k: [] for k in KINDS}
    for n in names:
        columns[n.split(":", 1)[0]].append(n)
    position = {
        n: (300 * KINDS.index(kind), 30 * row)
        for kind, members in columns.items()
        for row, n in enumerate(members)
    }
    nodes = [
        {
            "id": n,
            "name": label(n),
            "x": position[n][0],
            "y": position[n][1],
            "category": KINDS.index(n.split(":", 1)[0]),
            "symbolSize": 26 if n in hot else 12,
            "itemStyle": {"borderColor": "#c62828", "borderWidth": 4} if n in hot else {},
            "label": {
                "show": n in hot or n.startswith("role:"),
                "color": "#1f2937",
                "position": "right",
            },
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
                "layout": "none",
                "roam": True,
                "lineStyle": {"curveness": 0.15},
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
    replay_rows = [
        f"{f}: remaining"
        + (f" [{OVERDUE_LABEL}]" if f in c.overdue_blockers else "")
        + (f" [{OPEN_AT_END_LABEL}]" if f in c.open_at_end_blockers else "")
        for f in c.remaining
    ]
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


# --- Demo UI v2 (spec 006): verdict strip, swimlanes, diagnosis cards, ladder, scripted vs LLM --

OPEN_AT_END_STATE = OPEN_AT_END_LABEL.split(": ", 1)[0].removeprefix("owner obligation ")
SMALLEST_SAFE = "smallest safe repair"
TOP_RANKED = "top-ranked repair"
STATUS_CLASSES = (  # (label prefix, CSS class); the label text is always shown next to the colour
    (REPAIR_LABEL, "cg-status-repair"),
    ("reviewed (interpreted)", "cg-status-reviewed-interpreted"),
    ("reviewed", "cg-status-reviewed"),
    ("draft", "cg-status-draft"),
    ("illustrative", "cg-status-illustrative"),
)


def status_class(label: str) -> str:
    """The fixed CSS class for a clause status label (colour only; the label is still shown)."""
    return next((c for prefix, c in STATUS_CLASSES if label.startswith(prefix)), "cg-status-none")


@dataclass(frozen=True, slots=True)
class Chip:
    text: str  # clause id, or a fact id
    label: str  # the status label (clauses) or the data category (facts)
    css: str


def clause_chips(ids: Iterable[str], labels: dict[str, str]) -> tuple[Chip, ...]:
    return tuple(
        Chip(c, labels.get(c, "not loaded"), status_class(labels.get(c, "not loaded"))) for c in ids
    )


@dataclass(frozen=True, slots=True)
class Verdict:
    critical: int  # number of critical goals
    baseline_met: int  # critical goals met in the baseline
    baseline_failures: int
    repair_id: str  # "" when no complete replay ranked
    badge: str  # SMALLEST_SAFE, or "top-ranked repair (partial)"
    outcome: str  # engine wording: outcome, definition, masked count, caveats
    replay_met: int | None  # critical goals met in the best replay; None: no complete replay
    removed: int
    masked: int
    remaining: int
    new_conflicts: int
    caveat: str = ""  # the baseline's invalid_output caveat, shown even with nothing ranked


def critical_goals(scenario: Scenario) -> tuple[str, ...]:
    return tuple(g.id for g in scenario.recovery_goals if g.critical)


def _goals_met(result: RunResult, critical: tuple[str, ...]) -> int:
    met = dict(result.goals)
    return sum(1 for g in critical if met.get(g) is not None)


def badge(c: ReplayComparison, rank: int) -> str:
    """Rank 1 is "smallest safe repair" only if clean, complete and resolved (human decision
    2026-10-26); otherwise "top-ranked repair" with its outcome. Other ranks get no badge."""
    if rank != 1:
        return ""
    if not c.new_conflicts and not c.failed_steps and c.outcome == "resolved":
        return SMALLEST_SAFE
    return f"{TOP_RANKED} ({c.outcome})"


def verdict(baseline: RunResult, search_result: SearchResult, scenario: Scenario) -> Verdict:
    critical = critical_goals(scenario)
    head = (len(critical), _goals_met(baseline, critical), len(baseline.failures))
    caveat = baseline_caveat(baseline)
    if not search_result.ranked:
        return Verdict(*head, "", "", "no complete replay to rank", None, 0, 0, 0, 0, caveat)
    c = search_result.ranked[0]
    return Verdict(
        *head,
        repair_id=c.proposal.repair_id,
        badge=badge(c, 1),
        outcome=outcome_text(c),
        replay_met=_goals_met(c.replay, critical),
        removed=len(c.removed),
        masked=len(c.masked),
        remaining=len(c.remaining),
        new_conflicts=len(c.new_conflicts),
        caveat=caveat,
    )


def baseline_caveat(baseline: RunResult) -> str:
    """The engine's invalid_output caveat for the baseline alone (the same wording as
    `invalid_output_caveat`, which needs a comparison)."""
    steps = baseline.invalid_steps
    if not steps:
        return ""
    where = ", ".join(f"{role} at T+{m:02d} (baseline)" for m, role in steps)
    return (
        f"{len(steps)} steps with no decision (model returned invalid output): {where}; "
        "the result may depend on them"
    )


@dataclass(frozen=True, slots=True)
class Cell:
    minute: int
    recipient: bool  # the role received this inject
    facts: tuple[Chip, ...]  # facts that reached the role at this minute (inside its boundary)
    accepted: tuple[str, ...]
    rejected: tuple[str, ...]  # with reason codes
    statements: tuple[str, ...]  # always under the AGENT_STATEMENT label


@dataclass(frozen=True, slots=True)
class Bar:
    action: str
    source: Chip  # the clause or repair rule, with its status label
    start: int  # column index of opened_at
    end: int  # column index of the due minute (or the last column), inclusive
    opened: str  # "T+30"
    due: str  # "T+60" or "undetermined"
    state: str  # fulfilled at T+x | obligation_overdue (...) | obligation_missed (...) | open ...


@dataclass(frozen=True, slots=True)
class Lane:
    role: str
    cells: tuple[Cell, ...]
    bars: tuple[Bar, ...]


def _column(minutes: list[int], minute: int) -> int:
    """The last inject column at or before this minute."""
    return max((i for i, m in enumerate(minutes) if m <= minute), default=0)


def _bar_state(ob: ObligationStatus) -> str:
    owner = ob.clause_id.startswith(OWNER_RULE_PREFIX)
    if ob.missed:
        late = f"; fulfilled late at T+{ob.fulfilled_at:02d}" if ob.fulfilled_at is not None else ""
        kind = OBLIGATION_OVERDUE if owner else "obligation_missed"
        return f"{kind} (due T+{ob.due_at or 0:02d}){late}"
    if ob.fulfilled_at is not None:
        return f"fulfilled at T+{ob.fulfilled_at:02d}"
    return OPEN_AT_END_LABEL.split(": ", 1)[0] if owner else OPEN_AT_END_STATE


def swimlanes(result: RunResult, scenario: Scenario) -> list[Lane]:
    """One lane per role: the facts that reached it at each inject (only facts inside its
    boundary are ever released to it), what it did, and its obligations."""
    labels = dict(result.loaded_clauses)
    category = {f.id: f.data_category for e in scenario.events for f in e.facts}
    minutes = [e.at_minute for e in scenario.events]
    recipients = {e.at_minute: set(e.recipients) for e in scenario.events}
    lanes: list[Lane] = []
    for role in dict(result.boundaries):
        cells: list[Cell] = []
        for m in minutes:
            here = [e for e in result.log if e.minute == m and e.role == role]
            cells.append(
                Cell(
                    minute=m,
                    recipient=role in recipients[m],
                    facts=tuple(
                        Chip(e.detail, category.get(e.detail, ""), "cg-fact")
                        for e in here
                        if e.kind == "fact_released"
                    ),
                    accepted=tuple(
                        e.action + (f" -> {e.target}" if e.target else "")
                        for e in here
                        if e.kind == "accepted" and e.action
                    ),
                    rejected=tuple(
                        (e.action or "whole decision")
                        + (f" -> {e.target}" if e.target else "")
                        + (f" ({', '.join(e.reasons)})" if e.reasons else "")
                        for e in here
                        if e.kind == "rejected"
                    ),
                    statements=tuple(
                        e.detail if e.detail.startswith(AGENT_STATEMENT) else UNLABELLED
                        for e in here
                        if e.kind == "decision"
                    ),
                )
            )
        bars = tuple(
            Bar(
                action=ob.action,
                source=clause_chips((ob.clause_id,), labels)[0],
                start=_column(minutes, ob.opened_at),
                end=len(minutes) - 1 if ob.due_at is None else _column(minutes, ob.due_at),
                opened=f"T+{ob.opened_at:02d}",
                due="undetermined" if ob.due_at is None else f"T+{ob.due_at:02d}",
                state=_bar_state(ob),
            )
            for ob in result.obligations
            if ob.role in (role, "any")
        )
        lanes.append(Lane(role, tuple(cells), bars))
    return lanes


@dataclass(frozen=True, slots=True)
class DiagnosisItem:
    id: str
    description: str
    blocks: str
    qualification: str
    evidence: tuple[Chip, ...]


@dataclass(frozen=True, slots=True)
class CategoryCard:
    category: str
    items: tuple[DiagnosisItem, ...]  # empty: none found


def diagnosis_cards(result: RunResult) -> list[CategoryCard]:
    """One card per failure category (all five, in the taxonomy's order)."""
    labels = dict(result.loaded_clauses)
    return [
        CategoryCard(
            cat.value,
            tuple(
                DiagnosisItem(
                    f.id,
                    f.description,
                    ", ".join(f.goals),
                    f.qualification,
                    clause_chips(f.clause_ids, labels),
                )
                for f in result.failures
                if f.category is cat
            ),
        )
        for cat in FailureCategory
    ]


@dataclass(frozen=True, slots=True)
class Rung:
    rank: int
    repair_id: str
    badge: str
    outcome: str
    edits: int
    roles: tuple[str, ...]  # roles the edits touch
    removed: int
    masked: tuple[str, ...]
    new_conflicts: tuple[str, ...]
    authorization: str


def ladder(result: SearchResult) -> list[Rung]:
    out: list[Rung] = []
    for row, c in zip(repairs(result), result.ranked, strict=True):
        roles = sorted({r for e in c.proposal.edits for r in (e.role, e.counterpart) if r})
        out.append(
            Rung(
                rank=row.rank,
                repair_id=row.repair_id,
                badge=badge(c, row.rank),
                outcome=row.outcome,
                edits=row.edits,
                roles=tuple(roles),
                removed=row.removed,
                masked=row.masked,
                new_conflicts=row.new_conflicts,
                authorization=row.authorization,
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class EvaluationFinding:
    """A recorded, human-worded finding about one repair under one prompt version
    (`scenarios/<id>/evaluation_findings.yaml`)."""

    repair: str
    prompt_version: str
    scripted: str  # the scripted replay's outcome when the finding was recorded
    llm: str  # the LLM replay's outcome
    text: str
    source: str  # the document that records it


@dataclass(frozen=True, slots=True)
class AgentsRow:
    repair_id: str
    scripted: str  # outcome with its definition (engine wording)
    llm: str
    finding: str  # "" unless a recorded finding matches the repair and both computed verdicts
    source: str


def scripted_vs_llm(
    scripted: ReplayComparison,
    llm: ReplayComparison,
    prompt_version: str,
    recorded: Iterable[EvaluationFinding],
) -> AgentsRow:
    """The same repair under scripted and LLM agents. A recorded finding is shown only when it
    names this repair and exactly this prompt version (output mode and options included) and
    both verdicts match what was computed now."""
    if llm.proposal.repair_id != scripted.proposal.repair_id:
        raise ValueError("scripted and LLM comparisons must be for the same repair")
    match = next(
        (
            f
            for f in recorded
            if f.repair == scripted.proposal.repair_id
            and prompt_version == f.prompt_version
            and f.scripted == scripted.outcome
            and f.llm == llm.outcome
        ),
        None,
    )
    return AgentsRow(
        repair_id=scripted.proposal.repair_id,
        scripted=outcome_text(scripted),
        llm=outcome_text(llm),
        finding=match.text if match else "",
        source=match.source if match else "",
    )
