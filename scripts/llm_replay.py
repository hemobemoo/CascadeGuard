"""One live replay of a single repair with LLM agents, with a hard request cap (retries included).

Approved by the human for the golden successful repair (owner + share), cap 50, on the cached
v3 LLM baseline. Before any call, a dry run from the cache checks that the baseline is fully
cached and finds the first step the repair changes. During the run, any step that would call
the API before that point stops the run instead (it must be a cache hit). Prints which steps
were reused and which were live, the comparison with the scripted replay of the same repair,
requests, retries, failures (with their error detail) and cost. Never prints .env values.

    uv run python scripts/llm_replay.py [--repair ID] [--cap N]
"""

import argparse
import sys
import time
from dataclasses import dataclass, field, replace
from typing import Any

from cascadeguard.agents.cache import DEFAULT_CACHE_DIR, DecisionCache, cache_key
from cascadeguard.agents.llm import (
    CappedClient,
    DailyLimitReached,
    LLMAgent,
    LLMConfig,
    llm_agents,
    make_client,
)
from cascadeguard.cli import World, load_world, search_repairs, single_repair
from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.engine.repair_search import find_proposal
from cascadeguard.simulation.boundaries import RoleView

SCENARIO = "uae_health_access"
GOLDEN = (
    "owner.reverse_automated_lockouts.health_service_operator.30m"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)
STEPS = 36  # 6 injects x 6 roles


class StopRun(Exception):
    """A step before the repair's first change was not cached: stop before any call."""


def key_of(agent: LLMAgent, view: RoleView) -> str:
    return cache_key(agent.role_id, view, agent.prompt_version, agent.model, agent.schema)


def dry_keys(world: World, repair_id: str) -> tuple[list[str], list[str], int]:
    """Cache-only run: baseline keys, replay keys, and baseline steps not cached. No call."""
    dry_cache = DecisionCache(world.cache.directory if world.cache else DEFAULT_CACHE_DIR)
    agents: dict[str, Any] = {}
    seen: list[str] = []
    for rid, a in world.agents.items():
        assert isinstance(a, LLMAgent)
        offline = LLMAgent(
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
        agents[rid] = Keyed(offline, seen)
    dry = replace(world, agents=agents, cache=dry_cache)
    base = dry.baseline()
    missing = dry_cache.stats.misses
    p = find_proposal(base, dry.scenario, dry.roles, RuleBook(dry.clauses), repair_id)
    dry.replay(p)
    return seen[:STEPS], seen[STEPS:], missing


@dataclass
class Keyed:
    """Records the cache key of every step it is asked to decide."""

    agent: LLMAgent
    keys: list[str]

    @property
    def role_id(self) -> str:
        return self.agent.role_id

    def observe(self, view: RoleView) -> AgentDecision:
        self.keys.append(key_of(self.agent, view))
        return self.agent.observe(view)


@dataclass
class Step:
    index: int  # 0-35 baseline, 36-71 replay
    minute: int
    role: str
    source: str  # "cache" | "live" | "repeated failure"
    calls: int
    outcome: str


@dataclass
class Watched:
    """Live agent that refuses to call the API for a step before the first change."""

    agent: LLMAgent
    client: CappedClient
    cache: DecisionCache
    first_change: int  # replay index of the first changed step
    log: list[Step] = field(default_factory=list[Step])
    counter: list[int] = field(default_factory=lambda: [0])

    @property
    def role_id(self) -> str:
        return self.agent.role_id

    def observe(self, view: RoleView) -> AgentDecision:
        index = self.counter[0]
        self.counter[0] += 1
        replay_index = index - STEPS
        must_hit = index < STEPS or replay_index < self.first_change
        if must_hit and not self.cache.has(key_of(self.agent, view)):
            phase = "baseline" if index < STEPS else "replay"
            raise StopRun(f"{phase} step T+{view.minute:02d} {view.role_id} is not cached")
        before = self.client.requests
        decision = self.agent.observe(view)
        calls = self.client.requests - before
        outcome = decision.no_decision or "decision"
        source = (
            "live" if calls else ("repeated failure" if outcome == "request_failed" else "cache")
        )
        self.log.append(Step(index, view.minute, view.role_id, source, calls, outcome))
        return decision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", default=GOLDEN)
    parser.add_argument("--cap", type=int, default=50)
    args = parser.parse_args()

    config = LLMConfig.from_env()
    base_world = load_world(SCENARIO)
    roles = tuple(r.id for r in base_world.roles.roles)
    cache = DecisionCache(DEFAULT_CACHE_DIR)
    paced = make_client(config, cap=args.cap)
    client: CappedClient = paced.inner
    llm = llm_agents(roles, cache, config=config, client=paced)
    world = replace(base_world, agents=dict(llm), cache=cache)

    base_keys, replay_keys, missing = dry_keys(world, args.repair)
    if missing:
        print(f"STOP: the LLM baseline is not fully cached ({missing} steps); no call made.")
        return 2
    changed = [i for i, (b, r) in enumerate(zip(base_keys, replay_keys, strict=True)) if b != r]
    first = changed[0] if changed else STEPS
    order = [(e.at_minute, r) for e in world.scenario.events for r in roles]
    fm, fr = order[first] if changed else (None, None)
    print(f"Output mode: {config.output_mode}; repair: {args.repair}")
    print(
        f"Dry run: baseline fully cached; {len(changed)} of {STEPS} replay steps change; "
        f"first changed step: #{first} T+{fm:02d} {fr}"
    )

    counter = [0]
    log: list[Step] = []
    agents = {rid: Watched(a, client, cache, first, log, counter) for rid, a in llm.items()}
    live_world = replace(world, agents=dict(agents))
    started = time.monotonic()
    try:
        found = single_repair(live_world, args.repair)
    except StopRun as exc:
        print(f"STOP: {exc}. Requests sent: {client.requests}.")
        return 2
    except DailyLimitReached as exc:
        print(
            f"STOP: provider daily limit reached ({exc}). Requests sent: {client.requests}; "
            f"failures by type: {paced.failures}; wall clock {time.monotonic() - started:.0f} s."
        )
        return 2
    wall = time.monotonic() - started

    replay_steps = [s for s in log if s.index >= STEPS]
    print("")
    print(
        f"Baseline: {sum(s.source == 'cache' for s in log if s.index < STEPS)} of {STEPS} "
        "steps from the cache"
    )
    print("Replay steps (order of the run):")
    for s in replay_steps:
        mark = " <- first changed step" if s.index - STEPS == first else ""
        print(
            f"  #{s.index - STEPS:2} T+{s.minute:02d} {s.role:24} {s.source:16} "
            f"calls={s.calls} {s.outcome}{mark}"
        )
    before_hits = all(s.source == "cache" for s in replay_steps if s.index - STEPS < first)
    print(f"All replay steps before the first change were cache hits: {before_hits}")
    live = [s for s in replay_steps if s.source == "live"]
    asked_calls = sum(s.calls for s in live)
    output_retries = asked_calls - len(live) - paced.retries
    print(f"Replay: {len(replay_steps) - len(live)} from the cache, {len(live)} live")
    print(
        f"Requests: {client.requests} of {args.cap} (request retries: {paced.retries}; "
        f"invalid-output retries: {output_retries}; refused at the cap: {client.refused})"
    )
    print(f"Failed requests by type: {paced.failures or 'none'}")
    print(
        f"Wall clock: {wall:.0f} s (pacing waits {paced.paced_seconds:.0f} s, "
        f"backoff waits {paced.backoff_seconds:.0f} s)"
    )
    print(
        f"Tokens: {client.prompt_tokens} input, {client.completion_tokens} output; "
        f"cost {client.cost:.6f} credits (USD); time in API calls {client.seconds:.1f} s"
    )

    if not (found.ranked or found.inconclusive):
        print(f"Replay discarded by the hard filter: {[d.reason for d in found.discarded]}")
        return 0
    llm_c = found.comparison(args.repair)
    if llm_c.failed_steps:
        print(f"RESULT: {llm_c.outcome}")
        for run, m, r, why in llm_c.failed_steps:
            print(f"  {run} T+{m:02d} {r}: {why}")
    failures = [f for f in llm_c.replay.findings if f.kind == "no_decision"]
    print(f"no_decision findings in the replay: {len(failures)}")
    for f in failures:
        print(f"  T+{f.minute:02d} {f.role}: {f.detail}")
    if llm_c.failed_steps:
        return 0  # no comparison table for an inconclusive replay
    scripted = search_repairs(SCENARIO).comparison(args.repair).summary()
    mine = llm_c.summary()
    print("")
    print(f"{'':22} {'LLM replay':48} scripted replay")
    for k in (
        "outcome",
        "failures_removed",
        "failures_masked",
        "failures_remaining",
        "new_conflicts",
    ):
        print(f"{k:22} {mine[k]!s:48} {scripted[k]!s}")
    for goal, v in mine["goals"].items():
        print(
            f"goal {goal:17} {v['baseline'] + ' -> ' + v['replay']:48} "
            f"{scripted['goals'][goal]['baseline']} -> {scripted['goals'][goal]['replay']}"
        )
    if mine.get("new_conflict_tags"):
        print(f"new conflict tags (LLM): {mine['new_conflict_tags']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
