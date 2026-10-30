"""Command-line entry point.

cascadeguard run <scenario> [--clauses DIR] [--repair ID] [--export DIR] [--audit [DB]]
cascadeguard repairs <scenario> [--clauses DIR] [--export DIR]
Both take --agents scripted|llm (default scripted), --offline and --cache DIR (LLM only).
cascadeguard kb query "<text>" [-k N] | cascadeguard kb export <path>
"""

import argparse
import io
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from cascadeguard import __version__
from cascadeguard.agents.base import Agent
from cascadeguard.agents.cache import DEFAULT_CACHE_DIR, DecisionCache
from cascadeguard.agents.llm import (
    CAP_VARIABLE,
    DailyLimitReached,
    LLMAgent,
    LLMConfig,
    LLMConfigError,
    RetryPolicy,
    llm_agents,
)
from cascadeguard.agents.scripted import load_scripted_agents
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.repairs import RepairProposal
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.engine.repair_search import (
    INCONCLUSIVE_LISTED,
    MASKED_LABEL,
    OPEN_AT_END_LABEL,
    OVERDUE_LABEL,
    RANKING,
    SCRIPTED_LIMIT_NOTE,
    ReplayComparison,
    SearchResult,
    find_proposal,
    outcome_text,
    replay_one,
    search,
)
from cascadeguard.knowledge.kb import (
    Hit,
    KnowledgeBaseError,
    OpenRouterEmbedder,
    export_kb_main,
    index_digest,
    search_kb,
)
from cascadeguard.knowledge.loader import REVIEWED_DIR, load_clauses, load_engine_clauses
from cascadeguard.knowledge.retrieval import CONTEXT_LABEL
from cascadeguard.simulation.loader import (
    PROJECT_ROOT,
    SCENARIOS_DIR,
    check_clause_references,
    load_scenario,
)
from cascadeguard.simulation.orchestrator import SCRIPTED_AGENTS, RunResult, run
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
        "--live",
        action="store_true",
        help="with --repair and --agents llm: allow live (paid) calls for this one replay",
    )
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
        cmd.add_argument(
            "--cap",
            type=int,
            default=None,
            help=f"live LLM runs: max requests, retries included (or {CAP_VARIABLE} in .env)",
        )
        cmd.add_argument(
            "--extracted-context",
            action="store_true",
            help="LLM only: add keyword snippets of the non-book extracted PDFs to each prompt, "
            "labelled 'context only; not citable' (changes the prompt: no reuse of other runs)",
        )
        cmd.add_argument(
            "--kb-context",
            action="store_true",
            help="LLM only: add the top 3 vector knowledge-base chunks to each prompt, labelled "
            "'context only; not citable' (changes the prompt: no reuse of other runs)",
        )
    kb_cmd = subcommands.add_parser("kb", help="the vector knowledge base (context only)")
    kb_sub = kb_cmd.add_subparsers(dest="kb_command")
    query_cmd = kb_sub.add_parser("query", help="top-k chunks for a text, with file, page, label")
    query_cmd.add_argument("text")
    query_cmd.add_argument("-k", type=int, default=5, help="number of chunks (default 5)")
    export_cmd = kb_sub.add_parser(
        "export", help="write chunks, vectors and metadata as JSONL for a ChromaDB kb_main load"
    )
    export_cmd.add_argument("path", type=Path)
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
        result = run(
            self.scenario, self.roles, self.clauses, self.corpus_ids, self.agents, self.label
        )
        return replace(result, agents=self.agent_label)

    def replay(self, proposal: RepairProposal) -> RunResult:
        result = replay(
            self.scenario,
            self.roles,
            self.clauses,
            self.corpus_ids,
            self.agents,
            self.label,
            proposal,
        )
        return replace(result, agents=self.agent_label)


@dataclass(frozen=True, slots=True)
class AgentChoice:
    """Which agents play the roles. Scripted is the default and needs no key."""

    kind: str = SCRIPTED
    offline: bool = False
    cache_dir: Path = DEFAULT_CACHE_DIR
    extracted_context: bool = False  # P5-3: labelled snippets of non-book extracted PDFs
    cap: int | None = None  # live LLM runs: max requests, retries included
    kb_context: bool = False  # PR 3: labelled vector knowledge-base chunks


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
        llm = llm_agents(
            role_ids,
            cache,
            offline=True,
            model=LLMConfig.model_from_env(),
            extracted_context=choice.extracted_context,
            kb_context=choice.kb_context,
        )
        how = "offline: decision cache only"
    else:
        config = LLMConfig.from_env()  # missing variables are reported before the cap
        cap = choice.cap if choice.cap is not None else RetryPolicy.from_env().request_cap
        if cap is None:
            raise LLMConfigError(
                f"live LLM runs need a request cap: --cap N or {CAP_VARIABLE} in .env "
                "(requests, retries included)"
            )
        llm = llm_agents(
            role_ids,
            cache,
            config=config,
            extracted_context=choice.extracted_context,
            cap=cap,
            kb_context=choice.kb_context,
        )
        how = f"live calls through the decision cache, capped at {cap} requests"
    if choice.extracted_context:
        how += "; extracted-PDF context snippets (context only; not citable)"
    if choice.kb_context:
        index_digest()  # refuses a stale index before any step runs
        if not choice.offline:
            OpenRouterEmbedder()  # missing key or base URL: a clear message now, not mid-run
        how += "; vector knowledge-base chunks (context only; not citable)"
    mode = next(iter(llm.values())).output_mode
    # The model id is a .env value: it keys the cache but is never printed or exported.
    agent_label = f"LLM agents (model from CASCADEGUARD_MODEL; output mode {mode}; {how})"
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
        w.replay,
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
    """LLM runs only: steps that came from the cache, needed a call, or repeated a request
    failure, counted over everything this command ran (the baseline and any replays)."""
    if world.cache is None:
        return None
    st = world.cache.stats
    if not (st.hits or st.misses or st.failures_repeated):  # nothing ran (e.g. a refusal)
        return None
    line = (
        f"LLM decision cache (baseline and replays): {st.hits} steps reused, {st.misses} not cached"
    )
    if st.failures_repeated:
        line += f", {st.failures_repeated} repeated an earlier request failure"
    return line


LIVE_SEARCH_REFUSED = (
    "repair search with live LLM calls is not enabled (every candidate is replayed: hundreds of "
    "paid calls; needs explicit approval). Use --offline to search from cached decisions."
)
DAILY_LIMIT_STOP = "the provider's daily request limit was reached; the run was stopped."
LIVE_REPLAY_NEEDS_FLAG = (
    "a single-repair replay with live LLM calls needs --live (paid calls; needs approval)."
)


def single_repair(world: World, repair_id: str) -> SearchResult:
    """Replay one repair on this world (LLM agents): the baseline and that replay only."""
    return replay_one(
        world.baseline(),
        world.scenario,
        world.roles,
        RuleBook(world.clauses),
        world.replay,
        repair_id,
    )


def uncached_estimate(world: World, repair_id: str) -> tuple[int, int | None]:
    """Dry run from the cache only, no call: (baseline steps not cached, replay steps not
    cached). The replay count is None when the baseline is not fully cached (the repair can only
    be found from the real baseline). A lower bound: a live decision can change later views."""
    dry_cache = DecisionCache(world.cache.directory if world.cache else DEFAULT_CACHE_DIR)
    dry_agents: dict[str, Agent] = {
        rid: LLMAgent(
            a.role_id,
            a.model,
            None,
            dry_cache,
            a.known_roles,
            a.extracted_context,
            a.attempts,
            a.output_mode,
            kb_context=a.kb_context,
        )
        for rid, a in world.agents.items()
        if isinstance(a, LLMAgent)
    }
    dry = replace(world, agents=dry_agents, cache=dry_cache)
    base = dry.baseline()
    baseline_missing = dry_cache.stats.misses
    if baseline_missing:
        return baseline_missing, None
    p = find_proposal(base, dry.scenario, dry.roles, RuleBook(dry.clauses), repair_id)
    dry.replay(p)
    return 0, dry_cache.stats.misses - baseline_missing


def live_llm(world: World) -> bool:
    """Would running this world make live API calls? (Any LLM agent with a client.)"""
    return any(isinstance(a, LLMAgent) and a.client is not None for a in world.agents.values())


def format_result(result: RunResult, excluded_drafts: int | None = None) -> str:
    labels = dict(result.loaded_clauses)

    def cite(ids: tuple[str, ...]) -> str:
        """Every clause id is printed with its status label (or "not loaded")."""
        return ", ".join(f"{c} [{labels.get(c, 'not loaded')}]" for c in ids)

    lines = [f"Scenario: {result.scenario_id} (synthetic, hypothetical)"]
    lines.append(f"Clause set: {result.clause_set}")
    lines.append(f"Agents: {result.agents}")
    if result.failed_steps:
        lines.append(
            f"INCOMPLETE RUN: {len(result.failed_steps)} steps had no decision for infrastructure "
            "reasons: " + ", ".join(f"T+{m:02d} {r} ({why})" for m, r, why in result.failed_steps)
        )
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
    lines.append(f"Agents: {result.agents}")
    lines.append("Every repair rule is hypothetical. 'requires authorization': no reviewed,")
    lines.append("binding clause supports the permission it creates; it needs human and")
    lines.append("institutional approval.")
    if not result.ranked:
        lines.append(
            "  no complete replay to rank"
            if result.inconclusive
            else "  no candidate repair passed the hard filter"
        )
    for i, c in enumerate(result.ranked, 1):
        p = c.proposal
        auth = ", requires authorization" if p.requires_authorization else ""
        lines.append(f"{i:3}. {p.repair_id}")
        lines.append(
            f"     {outcome_text(c)}; critical blockers removed {c.critical_blockers_removed}; "
            f"{len(p.edits)} edit(s){auth}"
        )
        if c.masked:
            lines.append(f"     {MASKED_LABEL}: {', '.join(c.masked)}")
        if c.overdue_blockers:
            lines.append(f"     {OVERDUE_LABEL}: {', '.join(c.overdue_blockers)}")
        if c.open_at_end_blockers:
            lines.append(f"     {OPEN_AT_END_LABEL}: {', '.join(c.open_at_end_blockers)}")
        tags = c.conflict_tags()
        for fid in c.new_conflicts:
            tag = f"  [{tags[fid]}: {SCRIPTED_LIMIT_NOTE}]" if fid in tags else ""
            lines.append(f"     new conflict: {fid}{tag}")
    if result.inconclusive:
        lines.append("")
        lines.append("Inconclusive (unranked; not comparable: steps had no decision)")
        for c in result.inconclusive:
            auth = ", requires authorization" if c.proposal.requires_authorization else ""
            status = INCONCLUSIVE_LISTED.format(n=len(c.failed_steps))
            lines.append(
                f"  - {c.proposal.repair_id}: {status}; {len(c.proposal.edits)} edit(s){auth}"
            )
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
    if args.command == "kb":
        return _kb(args, parser)
    if args.command not in ("run", "repairs"):
        parser.print_help()
        return 0
    if args.kb_context and args.agents != LLM:  # human decision 2026-10-30: never silently ignored
        print("cascadeguard: --kb-context gives context to LLM agents only; use --agents llm")
        return 2
    choice = AgentChoice(
        args.agents, args.offline, args.cache, args.extracted_context, args.cap, args.kb_context
    )
    try:
        world = load_world(args.scenario, args.clauses, choice=choice)
    except (LLMConfigError, KnowledgeBaseError) as exc:
        print(f"cascadeguard: {exc}")
        return 2
    try:
        status = _main(args, world)
    except DailyLimitReached:  # fixed text: the provider's message is not printed here
        print(f"cascadeguard: {DAILY_LIMIT_STOP}")
        return 2
    except KnowledgeBaseError as exc:  # --kb-context lost the network mid-run
        print(f"cascadeguard: {exc}")
        return 2
    if (line := cache_line(world)) is not None:
        print(line)
    return status


def format_hits(hits: Sequence[Hit]) -> str:
    """Top-k chunks: score, file, page, span and label; then any reviewed clause whose quote is
    in the chunk, with that clause's own status label."""
    lines = [f"Knowledge base: {len(hits)} chunks ({CONTEXT_LABEL})"]
    for n, h in enumerate(hits, 1):
        c = h.chunk
        keyword = f"#{h.keyword_rank}" if h.keyword_rank is not None else "-"
        lines.append(
            f"{n}. {h.score:.4f} (vector #{h.vector_rank}, keyword {keyword})  "
            f"{c.source_file}  p.{c.page}  [{c.start}-{c.end}]"
        )
        lines.append(f"   label: {c.label}")
        lines.extend(f"   also in: {copy}" for copy in c.copies)
        lines.extend(f"   clause {r.id}: {r.status_label}" for r in c.clauses)
        lines.append(f"   {c.text[:300]}{'...' if len(c.text) > 300 else ''}")
    return "\n".join(lines)


def _kb(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    # Chunk text holds characters a legacy console code page cannot encode (cp1252 on Windows):
    # replace them rather than fail with a traceback (test-breaker round 3).
    stdout: object = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(errors="replace")
    try:
        if args.kb_command == "query":
            print(format_hits(search_kb(args.text, args.k)))
            return 0
        if args.kb_command == "export":
            count = export_kb_main(args.path)
            print(f"{count} chunks written to {_display(args.path)} (ChromaDB kb_main format)")
            return 0
    except KnowledgeBaseError as exc:
        print(f"cascadeguard: {exc}")
        return 2
    parser.print_help()
    return 0


def _main(args: argparse.Namespace, world: World) -> int:
    if args.command == "repairs" and live_llm(world):
        print(f"cascadeguard: {LIVE_SEARCH_REFUSED}")
        return 2
    if args.command == "run" and args.repair is not None:
        try:
            if world.cache is None:  # scripted: the full search, as before
                comparison = replay_repair(args.scenario, args.repair, world=world)
            else:  # LLM agents: this one repair only (P5-6)
                if live_llm(world):
                    base_missing, replay_missing = uncached_estimate(world, args.repair)
                    if replay_missing is None:
                        print(
                            f"cascadeguard: the LLM baseline is not fully cached ({base_missing} "
                            "steps); run and approve the baseline first."
                        )
                        return 2
                    print(
                        f"Uncached steps (dry run from the cache): {replay_missing} replay steps, "
                        f"each up to {RetryPolicy.from_env().max_requests_per_step} requests "
                        "(invalid-output retry x request retries); a lower bound, since a live "
                        "decision can change later views."
                    )
                    if not args.live:
                        print(f"cascadeguard: {LIVE_REPLAY_NEEDS_FLAG}")
                        return 2
                comparison = single_repair(world, args.repair).comparison(args.repair)
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
