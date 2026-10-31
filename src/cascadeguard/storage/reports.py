"""Generated evaluation documents (PR 5): the scripted trace export, the gap analysis and the
draft conclusion. Every number comes from an engine run or a committed export; nothing here
decides anything. `scripts/build_reports.py` writes the files; tests require the committed files
to equal what this module generates.

The conclusion draft is unpublished (human gate 7): nothing links to it until the human approves
its wording. The gap-example mapping is a draft too: only approved entries count as reviewed.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import model_validator

from cascadeguard.cli import World, baseline_markdown, excluded_drafts, load_world, search_repairs
from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.findings import CoordinationFailure
from cascadeguard.domain.policies import ClauseStatus, PolicyClause
from cascadeguard.domain.repairs import RepairProposal
from cascadeguard.engine.governance import GovernanceComparison
from cascadeguard.engine.repair_search import (
    REQUIRES_AUTHORIZATION_LABEL,
    ReplayComparison,
    SearchResult,
)
from cascadeguard.knowledge.loader import PROJECT_ROOT, load_clauses
from cascadeguard.simulation.loader import SCENARIOS_DIR
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.storage.export import (
    DISCLAIMER,
    comparison_export,
    comparison_markdown,
    governance_export,
    governance_markdown,
    run_export,
)

SCENARIO = "uae_health_access"
TRACES_DIR = PROJECT_ROOT / "docs" / "evaluation" / "traces"
GAP_ANALYSIS = PROJECT_ROOT / "docs" / "gap-analysis.md"
CONCLUSION_DRAFT = PROJECT_ROOT / "docs" / "review" / "pr5-conclusion-draft.md"
GATE4_DIR = PROJECT_ROOT / "docs" / "evaluation" / "gate4"
# Human wording (2026-10-31), used instead of "unauthorised" everywhere.
WITHOUT_AUTHORITY = "applied without the authority the governed engine requires"
SCRIPTED = "scripted agents"
NO_EXAMPLE = "No reviewed example clause is mapped to this failure."
LIVE_LLM = "live LLM agents, gate-4 recording"


class GapExample(DomainModel):
    failure: str
    clause: str
    relevance: str
    approved: bool = False


class GapExamples(DomainModel):
    status: Literal["draft", "reviewed"]
    entries: tuple[GapExample, ...]
    reviewed_by: str | None = None  # the human who approved the entries (gate 7)
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def _status_matches_approvals(self) -> Self:
        approved = bool(self.entries) and all(e.approved for e in self.entries)
        if (self.status == "reviewed") != approved:
            raise ValueError("status is reviewed exactly when every entry is approved")
        if self.status == "reviewed" and not (self.reviewed_by and self.reviewed_on):
            raise ValueError("a reviewed mapping names its reviewer and date")
        return self


def load_gap_examples(scenario: str = SCENARIO) -> GapExamples:
    path = SCENARIOS_DIR / scenario / "gap_examples.yaml"
    return GapExamples.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class ScriptedRuns:
    """The three scripted runs of the main comparison, from one world (like with like)."""

    world: World
    baseline: RunResult
    governance: GovernanceComparison
    search: SearchResult
    rank1: ReplayComparison


def scripted_runs(scenario: str = SCENARIO) -> ScriptedRuns:
    world = load_world(scenario)
    found = search_repairs(scenario, world=world)
    governance = world.governance_comparison()
    return ScriptedRuns(world, governance.governed, governance, found, found.ranked[0])


def _json(data: dict[str, Any]) -> str:
    """The same text `write_exports` writes."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def trace_files(runs: ScriptedRuns) -> dict[str, str]:
    """File name -> content for docs/evaluation/traces/: the governed baseline, the governance-off
    comparison and the rank-1 repair replay, all with scripted agents (the CLI's own exports)."""
    s = runs.baseline.scenario_id
    base = runs.baseline
    return {
        f"{s}-baseline.json": _json(run_export(base)),
        f"{s}-baseline.md": baseline_markdown(s, base, excluded_drafts(base)),
        f"{s}-governance-off.json": _json(governance_export(runs.governance)),
        f"{s}-governance-off.md": governance_markdown(runs.governance),
        f"{s}-replay-rank1.json": _json(comparison_export(runs.rank1)),
        f"{s}-replay-rank1.md": comparison_markdown(runs.rank1),
    }


def _label(clause: PolicyClause) -> str:
    return f"`{clause.id}` [{clause.status_label}]"


def _source(clause: PolicyClause) -> str:
    article = f", {clause.article}" if clause.article else ""
    return f"{clause.source_file}, p. {clause.page}{article}"


def _quote(clause: PolicyClause) -> list[str]:
    return [f"  > {line}" if line else "  >" for line in clause.text.strip().splitlines()]


def _repairs_for(failure_id: str, search: SearchResult) -> tuple[list[str], list[str]]:
    removing: list[str] = []
    masking: list[str] = []
    for rank, c in enumerate(search.ranked, 1):
        auth = f"; {REQUIRES_AUTHORIZATION_LABEL}" if c.proposal.requires_authorization else ""
        line = f"rank {rank} `{c.proposal.repair_id}` ({c.outcome}{auth})"
        if failure_id in c.removed:
            removing.append(line)
        elif failure_id in c.masked:
            masking.append(line)
    return removing, masking


def gap_analysis_markdown(
    runs: ScriptedRuns, examples: GapExamples, corpus: dict[str, PolicyClause]
) -> str:
    base = runs.baseline
    lines = [
        f"# Gap analysis: {base.scenario_id}",
        "",
        f"_{DISCLAIMER}_",
        "",
        "Generated from the governed baseline run with scripted agents "
        f"(clause set: {base.clause_set}) by `scripts/build_reports.py`; regenerate it, never "
        "edit it. Each diagnosed failure is a candidate for expert review, not a finding of law: "
        "its qualification below is part of it.",
        "",
        "The examples are a "
        + (
            "**DRAFT mapping awaiting the human's approval (gate 7)**"
            if examples.status == "draft"
            else f"mapping reviewed by the human ({examples.reviewed_by}, {examples.reviewed_on}, "
            "gate 7)"
        )
        + " (`scenarios/uae_health_access/gap_examples.yaml`). An entry not yet approved is "
        "marked so. Foreign and international texts are shown as examples of practice "
        "elsewhere, never as UAE law; every clause carries its status label.",
        "",
    ]
    for f in base.failures:
        lines += _failure_section(f, runs.search, examples, corpus, runs.world.clauses)
    return "\n".join(lines).rstrip("\n") + "\n"


def _failure_section(
    f: CoordinationFailure,
    search: SearchResult,
    examples: GapExamples,
    corpus: dict[str, PolicyClause],
    loaded: dict[str, PolicyClause],
) -> list[str]:
    lines = [
        f"## `{f.id}`",
        "",
        f"- Category: `{f.category.value}`; blocks {', '.join(f'`{g}`' for g in f.goals)}; "
        f"roles {', '.join(f'`{r}`' for r in f.roles)}.",
        f"- Diagnosis: {f.description}",
        f"- **Qualification:** _{f.qualification}_",
        "",
        "**UAE clauses considered by the engine:**",
        "",
    ]
    if not f.clause_ids:
        lines += ["- None found in the loaded clause set.", ""]
    for cid in f.clause_ids:
        c = corpus[cid]
        lines += [f"- {_label(c)}, {_source(c)}:", *_quote(c), ""]
    related = [
        c
        for c in loaded.values()
        if c.normalized is not None
        and c.normalized.action == f.subject
        and c.id not in f.clause_ids
    ]
    if related:
        lines += ["**Other loaded clauses on this action (not counted by the diagnosis):**", ""]
        for c in related:
            n = c.normalized
            assert n is not None
            condition = f"; condition: {n.condition}" if n.condition else ""
            lines.append(f"- {_label(c)}: read as a `{n.kind.value}` for `{n.action}`{condition}.")
        lines.append("")
    lines += ["**Examples (context, not UAE law; UAE principles are not binding):**", ""]
    entries = [e for e in examples.entries if e.failure == f.id]
    if not entries:
        lines += [f"- {NO_EXAMPLE}", ""]
    for e in entries:
        c = corpus[e.clause]
        state = "approved" if e.approved else "DRAFT, not yet approved"
        lines += [
            f"- {_label(c)}, {_source(c)} ({state}). Relevance: {e.relevance}",
            *_quote(c),
            "",
        ]
    removing, masking = _repairs_for(f.id, search)
    lines += [
        "**Repairs tested by replay (hypothetical rules, scripted agents):**",
        "",
        "- Remove its cause: " + ("; ".join(removing) if removing else "none") + ".",
        "- Only mask it (goal met another way; cause still present): "
        + ("; ".join(masking) if masking else "none")
        + ".",
        "",
    ]
    return lines


# --- Conclusion draft (gate 7, unpublished) ---------------------------------------------------


def _goals(result: RunResult) -> str:
    return "; ".join(
        f"`{g}` {'met at T+' + str(m) if m is not None else 'unmet'}" for g, m in result.goals
    )


def _ids(ids: Iterable[str]) -> str:
    return ", ".join(f"`{i}`" for i in ids) or "none"


def load_gate4() -> tuple[dict[str, Any], dict[str, Any]]:
    """The committed gate-4 exports (live LLM agents): the governed baseline and the comparison."""
    baseline = json.loads((GATE4_DIR / "baseline.json").read_text(encoding="utf-8"))
    off = json.loads((GATE4_DIR / "governance-off.json").read_text(encoding="utf-8"))
    return baseline, off


def _count(n: int) -> str:
    return {1: "one", 2: "two", 3: "three"}.get(n, str(n))


def _gate4_goals(goals: dict[str, str]) -> str:
    return "; ".join(f"`{g}` {v}" for g, v in sorted(goals.items()))


AUTHORITY_REASONS = frozenset({"no_authority", "authority_uncertain"})


def waived_actions(waived: list[dict[str, Any]]) -> str:
    """The waived actions, each with its reasons. The fixed phrase WITHOUT_AUTHORITY is true only
    if every one of them had an authority reason; anything else is an error, never a label."""
    for w in waived:
        if not AUTHORITY_REASONS & set(w["would_have_been_rejected"]):
            raise ValueError(
                f"{w['action']} at T+{w['minute']} was waived without an authority reason"
            )
    return "; ".join(
        f"T+{w['minute']} `{w['action']}` ({', '.join(w['would_have_been_rejected'])})"
        for w in waived
    )


def _minute(state: str) -> int | None:
    """'met at T+15' -> 15; 'unmet' -> None (the exports' goal text)."""
    return int(state.removeprefix("met at T+")) if state.startswith("met at T+") else None


def newly_met(governed: dict[str, int | None], ungoverned: dict[str, int | None]) -> list[str]:
    """Goals met in the ungoverned run but not in the governed one."""
    return [g for g, at in sorted(ungoverned.items()) if at is not None and governed.get(g) is None]


def met_here_not_in(
    governed: dict[str, int | None],
    ungoverned: dict[str, int | None],
    waived: list[dict[str, Any]],
    baseline: str,
) -> str:
    """A sentence for each goal met in the ungoverned run but not in `baseline`, saying whether it
    was met at the minute of a waived action (derived from the runs, never assumed)."""
    minutes = {w["minute"] for w in waived}
    parts: list[str] = []
    for goal in newly_met(governed, ungoverned):
        at = ungoverned[goal]
        when = f"at T+{at}"
        if at in minutes:
            when += f", the minute an action was {WITHOUT_AUTHORITY}"
        parts.append(f"`{goal}` is met in this run but not in the {baseline}, {when}.")
    return " ".join(parts)


def _gerund(action: str) -> str:
    """reverse_automated_lockouts -> 'reversing automated lockouts'."""
    verb, *rest = action.split("_")
    stem = verb[:-1] if verb.endswith("e") and not verb.endswith("ee") else verb
    return " ".join([stem + "ing", *rest])


def repair_label(p: RepairProposal) -> str:
    """The repair's edits in plain language, from their typed parameters only."""
    parts: list[str] = []
    for e in p.edits:
        op = e.operation.value
        if op == "assign_owner" and e.action:
            parts.append(
                f"make `{e.role}` the owner of {_gerund(e.action)} within "
                f"{e.deadline_minutes} minutes"
            )
        elif op == "define_minimum_data_share" and e.data_category and e.counterpart:
            category = e.data_category.replace("_", " ")
            parts.append(
                f"define a minimum share of {category} from `{e.role}` to `{e.counterpart}`"
            )
        else:  # the other grammar operations: named, never paraphrased
            parts.append(f"`{op}` for `{e.role}`")
    text = ", and ".join(parts)
    return text[0].upper() + text[1:]


def outcome_text(rep: ReplayComparison) -> str:
    met = (
        "all critical goals met"
        if not rep.unmet_critical_goals
        else f"critical goals unmet: {_ids(rep.unmet_critical_goals)}"
    )
    return (
        f"{met} (engine status: {rep.outcome}). {len(rep.removed)} failures removed at their "
        f"cause, {len(rep.masked)} masked with the cause still present"
    )


def same_failures(live: list[str], scripted: list[str]) -> str:
    if sorted(live) == sorted(scripted):
        return f"the same {len(live)} failures as with scripted agents"
    return (
        f"{len(live)} failures (scripted agents: {len(scripted)}; only live: "
        f"{_ids(sorted(set(live) - set(scripted)))}; only scripted: "
        f"{_ids(sorted(set(scripted) - set(live)))})"
    )


def conclusion_markdown(runs: ScriptedRuns, gate4: tuple[dict[str, Any], dict[str, Any]]) -> str:
    gov, off, rep = runs.baseline, runs.governance, runs.rank1
    waived = off.waived()
    p = rep.proposal
    live_base, live_off = gate4
    live_waived = live_off["would_have_been_rejected"]
    lines = [
        "# DRAFT conclusion wording (gate 7): not published",
        "",
        f"_{DISCLAIMER}_",
        "",
        "Status: **draft for the human's gate-7 decision.** Nothing links to this file and none "
        "of its wording is in the README or the demo until the human approves it. Generated by "
        "`scripts/build_reports.py` from the scripted traces in `docs/evaluation/traces/` and "
        "the gate-4 exports in `docs/evaluation/gate4/`.",
        "",
        "## Three runs of the same incident (scripted agents)",
        "",
        "All three runs use the same scripted agents, scenario and clause set "
        f"({gov.clause_set}), so they compare like with like.",
        "",
        f"1. **Governed** ({SCRIPTED}). The engine diagnoses {len(gov.failures)} coordination "
        f"failures: {_ids(f.id for f in gov.failures)}. Goals: {_goals(gov)}. Each failure is "
        "a candidate gap for expert review, not a confirmed legal or standards gap.",
        f"2. **Ungoverned** ({SCRIPTED}; governance off, a comparison mode, never the result). "
        f"{len(waived)} actions were {WITHOUT_AUTHORITY}: {waived_actions(waived)}. Goals: "
        f"{_goals(off.ungoverned)}. "
        + met_here_not_in(dict(gov.goals), dict(off.ungoverned.goals), waived, "governed baseline")
        + f" The causes of {_ids(off.masked())} are still present (masked, not removed).",
        f"3. **Governed with the rank-1 repair** ({SCRIPTED}; replay of the identical incident). "
        f"{repair_label(p)} (repair `{p.repair_id}`): {len(p.edits)} policy edits "
        f"(hypothetical rules, not source clauses: {_ids(e.operation.value for e in p.edits)}). "
        f"Outcome: **{outcome_text(rep)}**. Goals: {_goals(rep.replay)}. Removed at their cause: "
        f"{_ids(rep.removed)}. **Masked, cause still present:** {_ids(rep.masked)}. "
        + (
            f"The repair is marked {REQUIRES_AUTHORIZATION_LABEL}: it creates a permission that "
            "no reviewed, binding clause in the loaded clause set supports."
            if p.requires_authorization
            else ""
        ),
        "",
        "The ungoverned run is shown only together with the repair run: governance off meets "
        f"{_ids(newly_met(dict(gov.goals), dict(off.ungoverned.goals)))} by setting aside the "
        "engine's authority, prerequisite and information checks, while the repair meets every "
        "critical goal with the checks in force, through edits that still need institutional "
        "approval.",
        "",
        "## Supporting evidence: the same incident with a live model (live LLM agents)",
        "",
        "Recorded under gate 4 with live LLM agents (the model is set in `.env` and not named "
        "here; decisions replayable offline from `docs/evaluation/gate4/llm_cache/`). Not part "
        "of the comparison above: different agents.",
        "",
        f"- **Governed** ({LIVE_LLM}): the engine diagnoses "
        + same_failures([f["id"] for f in live_base["failures"]], [f.id for f in gov.failures])
        + ": "
        f"{_ids(f['id'] for f in live_base['failures'])}. Goals: "
        f"{_gate4_goals(live_base['goals'])}. Each failure is a candidate gap for expert "
        "review, not a confirmed legal or standards gap.",
        f"- **Ungoverned** ({LIVE_LLM}): {len(live_waived)} actions were {WITHOUT_AUTHORITY}: "
        f"{waived_actions(live_waived)}. Goals: "
        f"{_gate4_goals(live_off['ungoverned_run']['goals'])}. "
        + met_here_not_in(
            {g: _minute(v) for g, v in live_base["goals"].items()},
            {g: _minute(v) for g, v in live_off["ungoverned_run"]["goals"].items()},
            live_waived,
            "live governed run",
        )
        + " Causes still present: "
        f"{_ids(live_off['failures']['ungoverned_cause_still_present'])}.",
        "- Repair result (scripted agents, run 3 above): "
        + (
            "all critical goals were met"
            if not rep.unmet_critical_goals
            else f"critical goals unmet: {_ids(rep.unmet_critical_goals)}"
        )
        + f" with the engine's checks in force, through {_count(len(p.edits))} hypothetical "
        "policy edits"
        + (" that require institutional authorization" if p.requires_authorization else "")
        + ". No live repair replay was run (it would need a new gate-4 approval).",
        "",
    ]
    return "\n".join(lines)


def build(scenario: str = SCENARIO) -> dict[Path, str]:
    """Every generated file and its content."""
    runs = scripted_runs(scenario)
    corpus = {c.id: c for c in load_clauses()}
    examples = load_gap_examples(scenario)
    out = {TRACES_DIR / name: text for name, text in trace_files(runs).items()}
    out[GAP_ANALYSIS] = gap_analysis_markdown(runs, examples, corpus)
    out[CONCLUSION_DRAFT] = conclusion_markdown(runs, load_gate4())
    return out


def reviewed_example_clauses(examples: GapExamples, corpus: dict[str, PolicyClause]) -> bool:
    """Every mapped clause exists and is reviewed (never draft or illustrative)."""
    return all(
        e.clause in corpus and corpus[e.clause].status is ClauseStatus.REVIEWED
        for e in examples.entries
    )
