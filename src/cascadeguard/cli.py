"""Command-line entry point: `cascadeguard run <scenario> [--clauses DIR] [--repair ID]`."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from cascadeguard import __version__
from cascadeguard.agents.scripted import load_scripted_agents
from cascadeguard.knowledge.loader import REVIEWED_DIR, load_clauses, load_engine_clauses
from cascadeguard.simulation.loader import (
    PROJECT_ROOT,
    SCENARIOS_DIR,
    check_clause_references,
    load_scenario,
)
from cascadeguard.simulation.orchestrator import RunResult, run

REAL_CLAUSE_SET = "policies/reviewed: reviewed + illustrative clauses"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cascadeguard")
    parser.add_argument("--version", action="version", version=f"cascadeguard {__version__}")
    subcommands = parser.add_subparsers(dest="command")
    run_cmd = subcommands.add_parser("run", help="run a scenario with scripted agents")
    run_cmd.add_argument("scenario")
    run_cmd.add_argument(
        "--clauses",
        type=Path,
        default=None,
        help="load clauses from this directory instead of policies/reviewed (e.g. test fixtures)",
    )
    run_cmd.add_argument("--repair", default=None, help="replay with a repair (Phase 3)")
    return parser


def run_scenario(
    scenario_id: str, clauses_dir: Path | None = None, scenarios_dir: Path = SCENARIOS_DIR
) -> RunResult:
    """Run the baseline with ScriptedAgents. Fixture clause sets are labelled as such."""
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
    agents = load_scripted_agents(
        scenarios_dir / scenario_id / "scripted_decisions.yaml", scenario, roles
    )
    return run(scenario, roles, clauses, corpus_ids, agents, label)


def _display(path: Path) -> str:
    """Project-relative path when possible, so labels do not depend on the checkout location."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def format_result(result: RunResult, excluded_drafts: int | None = None) -> str:
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
            cites = f"  [{', '.join(e.clause_ids)}]" if e.clause_ids else ""
            detail = f"  {e.detail}" if e.detail else ""
            lines.append(f"  {e.kind.upper():8} {e.role}: {what}{target}{why}{cites}{detail}")
        elif e.kind.startswith("obligation_") or e.kind == "goal_met":
            subject = e.detail or e.action or ""
            cites = f"  [{', '.join(e.clause_ids)}]" if e.clause_ids else ""
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
        lines.append(f"  {o.clause_id}: {o.role} {o.action}, due {due}, {state}")
    lines.append("")
    lines.append("Recovery goals")
    for goal, met in result.goals:
        lines.append(f"  {goal}: {'met at T+' + str(met) if met is not None else 'UNMET'}")
    lines.append("")
    lines.append("Findings")
    for f in result.findings:
        lines.append(f"  T+{f.minute:02d} {f.kind}: {f.detail}")

    labels = dict(result.loaded_clauses)
    lines.append("")
    lines.append("Diagnosed coordination failures")
    if not result.failures:
        lines.append("  none")
    for f in result.failures:
        lines.append(f"  [{f.category.value}] {f.subject}")
        lines.append(f"    {f.description}")
        lines.append(f"    blocks: {', '.join(f.goals)}; roles: {', '.join(f.roles)}")
        if f.clause_ids:
            cited = ", ".join(f"{c} [{labels.get(c, 'not loaded')}]" for c in f.clause_ids)
            lines.append(f"    clauses: {cited}")
        lines.append(f"    {f.qualification}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        if args.repair is not None:
            print("cascadeguard run --repair: not implemented yet (Phase 3).")
            return 2
        result = run_scenario(args.scenario, args.clauses)
        excluded = None
        if args.clauses is None:
            loaded = {cid for cid, _ in result.loaded_clauses}
            excluded = sum(1 for c in load_clauses(REVIEWED_DIR) if c.id not in loaded)
        print(format_result(result, excluded))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
