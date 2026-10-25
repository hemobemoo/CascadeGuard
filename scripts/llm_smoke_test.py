"""Phase 5 smoke test: exactly ONE live LLM call, for one role at one inject (gate 4: paid).

Every other step of the incident is played by the scripted agents, so the engine judges the
LLM decision in the real state of the run. No retry: the human approved one call. Prints
latency, tokens, cost (OpenRouter usage data), whether the reply validated against
AgentDecision, whether its citations passed the engine, and a cost estimate for one full
scenario run. Never prints the model id or any other .env value.

    uv run python scripts/llm_smoke_test.py [--role ROLE] [--minute N]
"""

import argparse
import sys
from typing import Any

from cascadeguard.agents.cache import DEFAULT_CACHE_DIR, DecisionCache, cache_key
from cascadeguard.agents.llm import (
    PROMPT_VERSION,
    DailyLimitReached,
    LLMAgent,
    LLMConfig,
    build_messages,
    make_client,
    response_schema,
)
from cascadeguard.cli import load_world, search_repairs
from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.engine.constraints import Reason
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.orchestrator import run

CITATION_REASONS = {
    Reason.UNKNOWN_CITATION.value,
    Reason.DRAFT_CITATION.value,
    Reason.CITATION_OUT_OF_SCOPE.value,
}


class OneStep:
    """Scripted everywhere except one (role, minute), which goes to the LLM agent once."""

    def __init__(self, scripted: Any, llm: LLMAgent, minute: int) -> None:
        self.role_id = llm.role_id
        self.scripted, self.llm, self.minute = scripted, llm, minute
        self.decision: AgentDecision | None = None
        self.used = 0

    def observe(self, view: RoleView) -> AgentDecision:
        if view.minute != self.minute:
            return self.scripted.observe(view)
        self.used += 1
        assert self.used == 1, "the smoke test makes one call only"
        self.decision = self.llm.observe(view)
        return self.decision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="uae_health_access")
    parser.add_argument("--role", default="health_service_operator")
    parser.add_argument("--minute", type=int, default=15)
    args = parser.parse_args()

    config = LLMConfig.from_env()  # raises naming missing variables, never values
    world = load_world(args.scenario)
    if args.minute not in {e.at_minute for e in world.scenario.events}:
        print(f"T+{args.minute} is not an inject minute")
        return 2
    role_ids = tuple(r.id for r in world.roles.roles)
    cache = DecisionCache(DEFAULT_CACHE_DIR)
    llm = LLMAgent(
        args.role,
        config.model,
        make_client(config, cap=1),  # one approved call: retries stop at the cap
        cache,
        role_ids,
        attempts=1,
        output_mode=config.output_mode,
        redact=(config.api_key,),
    )
    step = OneStep(world.agents[args.role], llm, args.minute)
    agents = {**world.agents, args.role: step}
    try:
        result = run(
            world.scenario, world.roles, world.clauses, world.corpus_ids, agents, world.label
        )
    except DailyLimitReached as exc:  # message already redacted; nothing chained
        print(f"STOP: provider daily limit reached ({exc}).")
        return 2

    decision, usage = step.decision, llm.last_usage
    print(f"Smoke test: {args.role} at T+{args.minute:02d} (model from CASCADEGUARD_MODEL)")
    print(f"Output mode: {config.output_mode}")
    if usage is None:
        print("Served from the decision cache: no call was made.")
    else:
        print(f"API calls made: {usage.calls}")
        print(f"Latency: {usage.latency_seconds:.2f} s")
        print(f"Input tokens: {usage.prompt_tokens}; output tokens: {usage.completion_tokens}")
        cost = "not reported" if usage.cost is None else f"{usage.cost:.6f} credits (USD)"
        print(f"Cost (OpenRouter usage): {cost}")
    if llm.last_error:
        print(f"Request error: {llm.last_error}")
    assert decision is not None
    validated = decision.no_decision is None
    print(f"Validated against AgentDecision: {'yes' if validated else 'no'}", end="")
    print("" if validated else f" (no decision: {decision.no_decision})")
    if validated:
        print(f"Proposed actions: {[a.action_type for a in decision.proposed_actions]}")
        print(f"Cited clauses: {[c.clause_id for c in decision.citations]}")
        print(f"Gap claims: {len(decision.gap_claims)}")
        mine = [f for f in result.findings if f.minute == args.minute and f.role == args.role]
        bad = [f for f in mine if f.kind in CITATION_REASONS]
        print(
            "Citations passed the engine: "
            + ("yes" if not bad else "no: " + "; ".join(f"{f.kind} {f.clause_ids}" for f in bad))
        )
        for e in result.log:
            if (
                e.minute == args.minute
                and e.role == args.role
                and e.kind in ("accepted", "rejected")
            ):
                why = f" ({', '.join(e.reasons)})" if e.reasons else ""
                print(f"  {e.kind.upper()} {e.action or 'whole decision'}{why}")
        other = [f.kind for f in mine if f.kind not in CITATION_REASONS]
        if other:
            print(f"Other findings for this step: {other}")

    if usage is not None and usage.prompt_tokens:
        estimate(
            world,
            args.role,
            args.minute,
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.cost,
            config.output_mode,
        )
    return 0


def estimate(
    world: Any,
    role: str,
    minute: int,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float | None,
    mode: str,
) -> None:
    """Scale the one call to a full run by prompt size (characters), with the same output size.
    The repair search estimate counts the distinct views over all scripted replays: an upper
    bound proxy, since LLM decisions may change later views differently."""
    base = world.baseline()
    roles = tuple(r.id for r in world.roles.roles)
    chars = {
        (v.role_id, v.minute): sum(
            len(m["content"]) for m in build_messages(v, roles, output_mode=mode)
        )
        for v in base.views
    }
    per_char = prompt_tokens / chars[(role, minute)]
    run_prompt = sum(chars.values()) * per_char
    run_completion = completion_tokens * len(chars)
    print("")
    print(f"Estimate for one full baseline run ({len(chars)} steps, no cache hits):")
    print(f"  ~{run_prompt:,.0f} input tokens, ~{run_completion:,.0f} output tokens")
    schema = response_schema()

    def key(v: RoleView) -> str:
        return cache_key(v.role_id, v, PROMPT_VERSION, "estimate", schema)

    seen = {key(v) for v in base.views}
    found = search_repairs(world.scenario.id)
    extra = 0
    for c in found.ranked:
        for v in c.replay.views:
            if (k := key(v)) not in seen:
                seen.add(k)
                extra += 1
    print(f"Repair search (scripted proxy): {len(found.ranked)} replays, ~{extra} uncached steps")
    if cost is None:
        print("  cost not reported by the provider; cannot estimate in credits")
        return
    in_rate_cost = cost * (run_prompt + run_completion) / (prompt_tokens + completion_tokens)
    print(f"  baseline: ~{in_rate_cost:.6f} credits (USD)")
    print(f"  repair search on top: ~{in_rate_cost * extra / len(chars):.6f} credits (USD)")


if __name__ == "__main__":
    sys.exit(main())
