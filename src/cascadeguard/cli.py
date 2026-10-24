"""Command-line entry point.

cascadeguard run <scenario> [--clauses DIR] [--repair ID] [--export DIR] [--audit [DB]]
cascadeguard repairs <scenario> [--clauses DIR] [--export DIR]
Both take --agents scripted|llm (default scripted), --offline and --cache DIR (LLM only).
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cascadeguard import __version__
from cascadeguard.agents.base import Agent
from cascadeguard.agents.cache import DEFAULT_CACHE_DIR, DecisionCache
from cascadeguard.agents.llm import LLMConfig, LLMConfigError, llm_agents
from cascadeguard.agents.scripted import load_scripted_agents
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.engine.repair_search import (
    MASKED_LABEL,
    RANKING,
    SCRIPTED_LIMIT_NOTE,
    ReplayComparison,
    SearchResult,
    search,
)
from cascadeguard.knowledge.loader import REVIEWED_DIR, load_clauses, load_engine_clauses
from cascadeguard.simulation.loader import (
    PROJECT_ROOT,
    SCENARIOS_DIR,
    check_clause_references,
    load_scenario,
)
from cascadeguard.simulation.orchestrator import RunResult, run
from cascadeguard.simulation.replay import replay
from cascadeguard.storage.audit import DEFAULT_DB, AuditStore
from cascadeguard.storage.export import (
    DISCLAIMER,
    comparison_export,
    comparison_markdown,
    run_export,
    search_export,
    write_exports,
)

REAL_CLAUSE_SET = "policies/reviewed: reviewed + illustrative clauses"
SCRIPTED = "scripted"
LLM = "llm"
SCRIPTED_AGENTS = "scripted agents (scripted_decisions.yaml)"


def _display(path: Path) -> str:
    """Project-relative path when possible, so labels do not depend on the checkout location."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cascadeguard")
    parser.add_argument("--version", action="version", version=f"cascadeguard {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    run_cmd = subcommands.add_parser("run", help="run a scenario (scripted agents by default)")
    run_cmd.add_argument("scenario")
    run_cmd.add_argument(
        "--clauses",
        type=Path,
        default=None,
        help="load clauses from this directory instead of policies/reviewed (e.g. test fixtures)",
    )
    run_cmd.add_argument(
        "--repair", default=None, help="replay the identical incident with this repair id"
    )
    run_cmd.add_argument("--export", type=Path, default=None, help="write JSON and Markdown here")
    run_cmd.add_argument(
        "--audit",
        type=Path,
        nargs="?",
        const=DEFAULT_DB,
        default=None,
        help=f"record the run in a DuckDB audit file (default {_display(DEFAULT_DB)})",
    )
    repairs_cmd = subcommands.add_parser("repairs", help="search and rank candidate repairs")
    repairs_cmd.add_argument("scenario")
    repairs_cmd.add_argument("--clauses", type=Path, default=None)
    repairs_cmd.add_argument("--export", type=Path, default=None)
    repairs_cmd.add_argument("--audit", type=Path, nargs="?", const=DEFAULT_DB, default=None)
    for cmd in (run_cmd, repairs_cmd):
        cmd.add_argument(
            "--agents",
            choices=(SCRIPTED, LLM),
            default=SCRIPTED,
            help="who plays the roles: scripted decisions (default, no key) or the LLM in .env",
        )
        cmd.add_argument(
            "--offline",
            action="store_true",
            help="LLM agents from the decision cache only: no API call, no key needed",
        )
        cmd.add_argument(
            "--cache",
            type=Path,
            default=DEFAULT_CACHE_DIR,
            help=f"LLM decision cache directory (default {_display(DEFAULT_CACHE_DIR)})",
        )
    return parser


@dataclass(frozen=True, slots=True)
class World:
    """Everything a run needs. A replay changes only what its repair changes."""

    scenario: Scenario
    roles: RoleSet
    clauses: dict[str, PolicyClause]
    corpus_ids: frozenset[str]
    agents: dict[str, Agent]
    label: str
    agent_label: str = SCRIPTED_AGENTS
    cache: DecisionCache | None = None  # LLM agents only

    def baseline(self) -> RunResult:
        return run(
            self.scenario, self.roles, self.clauses, self.corpus_ids, self.agents, self.label
        )


@dataclass(frozen=True, slots=True)
class AgentChoice:
    """Which agents play the roles. Scripted is the default and needs no key."""

    kind: str = SCRIPTED
    offline: bool = False
    cache_dir: Path = DEFAULT_CACHE_DIR


SCRIPTED_CHOICE = AgentChoice()


def load_world(
    scenario_id: str,
    clauses_dir: Path | None = None,
    scenarios_dir: Path = SCENARIOS_DIR,
    choice: AgentChoice = SCRIPTED_CHOICE,
) -> World:
    corpus = load_clauses(REVIEWED_DIR)
    if clauses_dir is None:
        clauses = load_engine_clauses(REVIEWED_DIR)
        label = REAL_CLAUSE_SET
    else:
        clauses = load_engine_clauses(clauses_dir)
        label = f"SYNTHETIC FIXTURES from {_display(clauses_dir)}, not the real corpus"
    corpus_ids = frozenset(c.id for c in corpus)
    scenario, roles = load_scenario(scenario_id, set(corpus_ids), scenarios_dir)
    check_clause_references(clauses.values(), roles)
    if choice.kind == SCRIPTED:
        scripted = load_scripted_agents(
            scenarios_dir / scenario_id / "scripted_decisions.yaml", scenario, roles
        )
        return World(scenario, roles, clauses, corpus_ids, dict(scripted), label)
    cache = DecisionCache(choice.cache_dir)
    role_ids = tuple(r.id for r in roles.roles)
    if choice.offline:  # the model id is still needed to find its cache entries
        llm = llm_agents(role_ids, cache, offline=True, model=LLMConfig.model_from_env())
        how = "offline: decision cache only"
    else:
        llm = llm_agents(role_ids, cache)
        how = "live calls through the decision cache"
    # The model id is a .env value: it keys the cache but is never printed or exported.
    agent_label = f"LLM agents (model from CASCADEGUARD_MODEL; {how})"
    return World(scenario, roles, clauses, corpus_ids, dict(llm), label, agent_label, cache)


def run_scenario(
    scenario_id: str,
    clauses_dir: Path | None = None,
    scenarios_dir: Path = SCENARIOS_DIR,
    choice: AgentChoice = SCRIPTED_CHOICE,
) -> RunResult:
    """Run the baseline (ScriptedAgents by default). Fixture clause sets are labelled as such."""
    return load_world(scenario_id, clauses_dir, scenarios_dir, choice).baseline()


def search_repairs(
    scenario_id: str,
    clauses_dir: Path | None = None,
    scenarios_dir: Path = SCENARIOS_DIR,
    choice: AgentChoice = SCRIPTED_CHOICE,
    world: World | None = None,
) -> SearchResult:
    """Replay every candidate repair on the identical incident and rank them."""
    w = world or load_world(scenario_id, clauses_dir, scenarios_dir, choice)
    return search(
        w.baseline(),
        w.scenario,
        w.roles,
        RuleBook(w.clauses),
        lambda p: replay(w.scenario, w.roles, w.clauses, w.corpus_ids, w.agents, w.label, p),
    )


def replay_repair(
    scenario_id: str,
    repair_id: str,
    clauses_dir: Path | None = None,
    scenarios_dir: Path = SCENARIOS_DIR,
    choice: AgentChoice = SCRIPTED_CHOICE,
    world: World | None = None,
) -> ReplayComparison:
    found = search_repairs(scenario_id, clauses_dir, scenarios_dir, choice, world)
    return found.comparison(repair_id)


def cache_line(world: World) -> str | None:
    """LLM runs only: how many steps came from the cache and how many needed a call."""
    if world.cache is None:
        return None
    st = world.cache.stats
    return f"LLM decision cache: {st.hits} steps reused, {st.misses} not cached"


def format_result(result: RunResult, excluded_drafts: int | None = None) -> str:
    labels = dict(result.loaded_clauses)

    def cite(ids: tuple[str, ...]) -> str:
        """Every clause id is printed with its status label (or "not loaded")."""
        return ", ".join(f"{c} [{labels.get(c, 'not loaded')}]" for c in ids)

    lines = [f"Scenario: {result.scenario_id} (synthetic, hypothetical)"]
    lines.append(f"Clause set: {result.clause_set}")
    lines.append(f"  {len(result.loaded_clauses)} clauses loaded")
    if excluded_drafts:
        lines.append(f"  {excluded_drafts} draft clauses not loaded (awaiting human review)")
        lines.append("  Decisions citing drafts are rejected; diagnosis covers loaded clauses only")
    lines += [f"  - {cid} [{label}]" for cid, label in result.loaded_clauses]

    lines.append("")
    lines.append("Timeline")
    for e in result.log:
        if e.kind == "inject":
            lines.append(f"T+{e.minute:02d}  {e.detail}")
        elif e.kind in ("accepted", "rejected"):
            what = e.action or "whole decision"
            target = f" -> {e.target}" if e.target else ""
            why = f"  ({', '.join(e.reasons)})" if e.reasons else ""
            cites = f"  {{{cite(e.clause_ids)}}}" if e.clause_ids else ""
            detail = f"  {e.detail}" if e.detail else ""
            lines.append(f"  {e.kind.upper():8} {e.role}: {what}{target}{why}{cites}{detail}")
        elif e.kind.startswith("obligation_") or e.kind == "goal_met":
            subject = (
                e.detail
                if e.kind == "goal_met"
                else (e.action or "") + (f" ({e.detail})" if e.detail else "")
            )
            cites = f"  {{{cite(e.clause_ids)}}}" if e.clause_ids else ""
            lines.append(f"  {e.kind:8} {e.role}: {subject}{cites}")

    lines.append("")
    lines.append("Obligations")
    for o in result.obligations:
        due = f"T+{o.due_at}" if o.due_at is not None else "undetermined"
        state = (
            f"fulfilled T+{o.fulfilled_at}"
            if o.fulfilled_at is not None
            else ("missed" if o.missed else "open")
        )
        firm = "" if o.firm else ", uncertain (binding unknown)"
        lines.append(f"  {cite((o.clause_id,))}: {o.role} {o.action}, due {due}, {state}{firm}")
    lines.append("")
    lines.append("Recovery goals")
    for goal, met in result.goals:
        lines.append(f"  {goal}: {'met at T+' + str(met) if met is not None else 'UNMET'}")
    lines.append("")
    lines.append("Findings")
    for f in result.findings:
        cites = f"  {{{cite(f.clause_ids)}}}" if f.clause_ids else ""
        lines.append(f"  T+{f.minute:02d} {f.kind}: {f.detail}{cites}")

    lines.append("")
    lines.append("Diagnosed coordination failures")
    if not result.failures:
        lines.append("  none")
    for f in result.failures:
        lines.append(f"  [{f.category.value}] {f.subject}")
        lines.append(f"    {f.description}")
        if f.clause_ids:  # right after the description, which may name them
            lines.append(f"    clauses: {cite(f.clause_ids)}")
        lines.append(f"    blocks: {', '.join(f.goals)}; roles: {', '.join(f.roles)}")
        lines.append(f"    {f.qualification}")
    return "\n".join(lines)


def format_search(result: SearchResult) -> str:
    labels = dict(result.loaded_clauses)
    lines = ["Candidate repairs, ranked (lexicographic; see AGENTS.md and ADR 0001)"]
    lines.append(f"Order: {RANKING}")
    lines.append(f"Clause set: {result.clause_set}")
    lines.append("Every repair rule is hypothetical. 'requires authorization': no reviewed,")
    lines.append("binding clause supports the permission it creates; it needs human and")
    lines.append("institutional approval.")
    if not result.ranked:
        lines.append("  no candidate repair passed the hard filter")
    for i, c in enumerate(result.ranked, 1):
        p = c.proposal
        auth = ", requires authorization" if p.requires_authorization else ""
        lines.append(f"{i:3}. {p.repair_id}")
        lines.append(
            f"     {c.outcome}; critical blockers removed {c.critical_blockers_removed}; "
            f"{len(p.edits)} edit(s){auth}"
        )
        if c.masked:
            lines.append(f"     {MASKED_LABEL}: {', '.join(c.masked)}")
        tags = c.conflict_tags()
        for fid in c.new_conflicts:
            tag = f"  [{tags[fid]}: {SCRIPTED_LIMIT_NOTE}]" if fid in tags else ""
            lines.append(f"     new conflict: {fid}{tag}")
    lines.append("")
    lines.append("Discarded by the hard filter")
    if not result.discarded:
        lines.append("  none")
    for d in result.discarded:
        cites = ", ".join(f"{c} [{labels.get(c, 'not loaded')}]" for c in d.clause_ids)
        lines.append(f"  {d.repair_id}: {d.reason}: {cites}")
    return "\n".join(lines)


def _export(directory: Path, name: str, data: dict[str, Any], markdown: str) -> None:
    for path in write_exports(directory, name, data, markdown):
        print(f"exported {_display(path)}")


def _text_markdown(title: str, text: str) -> str:
    return f"# {title}\n\n_{DISCLAIMER}_\n\n```text\n{text}\n```\n"


def excluded_drafts(result: RunResult) -> int:
    """Corpus clauses the real clause set left out (drafts awaiting human review)."""
    loaded = {cid for cid, _ in result.loaded_clauses}
    return sum(1 for c in load_clauses(REVIEWED_DIR) if c.id not in loaded)


def baseline_markdown(scenario_id: str, result: RunResult, excluded: int | None) -> str:
    """The baseline Markdown export, shared by the CLI and the UI."""
    return _text_markdown(f"Baseline: {scenario_id}", format_result(result, excluded))


def search_markdown(scenario_id: str, result: SearchResult) -> str:
    """The repair-search Markdown export, shared by the CLI and the UI."""
    return _text_markdown(f"Repairs: {scenario_id}", format_search(result))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command not in ("run", "repairs"):
        parser.print_help()
        return 0
    choice = AgentChoice(args.agents, args.offline, args.cache)
    try:
        world = load_world(args.scenario, args.clauses, choice=choice)
    except LLMConfigError as exc:
        print(f"cascadeguard: {exc}")
        return 2
    if choice.kind != SCRIPTED:  # scripted output stays exactly as before
        print(f"Agents: {world.agent_label}")
    status = _main(args, world)
    if (line := cache_line(world)) is not None:
        print(line)
    return status


def _main(args: argparse.Namespace, world: World) -> int:
    if args.command == "run" and args.repair is not None:
        try:
            comparison = replay_repair(args.scenario, args.repair, world=world)
        except KeyError as exc:
            print(f"cascadeguard: {exc.args[0]}. List repairs with `cascadeguard repairs`.")
            return 2
        markdown = comparison_markdown(comparison)
        print(markdown)
        if args.export is not None:
            _export(
                args.export,
                f"{args.scenario}-replay-{args.repair}",
                comparison_export(comparison),
                markdown,
            )
        if args.audit is not None:
            store = AuditStore(args.audit)
            try:
                base, rep = store.record_comparison(comparison)
            finally:
                store.close()
            print(f"audit: baseline run {base}, replay run {rep} in {_display(args.audit)}")
        return 0
    if args.command == "run":
        result = world.baseline()
        excluded = excluded_drafts(result) if args.clauses is None else None
        print(format_result(result, excluded))
        if args.export is not None:
            _export(
                args.export,
                f"{args.scenario}-baseline",
                run_export(result),
                baseline_markdown(args.scenario, result, excluded),
            )
        if args.audit is not None:
            store = AuditStore(args.audit)
            try:
                run_id = store.record_run(result, "baseline")
            finally:
                store.close()
            print(f"audit: baseline run {run_id} in {_display(args.audit)}")
        return 0
    if args.command == "repairs":
        found = search_repairs(args.scenario, world=world)
        print(format_search(found))
        if args.export is not None:
            _export(
                args.export,
                f"{args.scenario}-repairs",
                search_export(found),
                search_markdown(args.scenario, found),
            )
        if args.audit is not None:
            store = AuditStore(args.audit)
            try:
                base = store.record_search(world.baseline(), found)
            finally:
                store.close()
            print(f"audit: baseline run {base} and its candidates in {_display(args.audit)}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
