"""One full LLM baseline (no repairs) with a hard cap on API requests, retries included.

Approved by the human for uae_health_access, capped at 72 requests. The cap is enforced in a
client wrapper before anything reaches the network: once reached, every further step is a
`request_failed` no-decision and no call is made. Decisions go through the normal cache
(data/llm_cache/), so later offline runs and replays reuse them. Prints completed steps,
no-decision findings, rejected citations, tokens, total cost (OpenRouter usage data) and the
diagnosis compared with the scripted baseline. Never prints the model id or another .env value.

    uv run python scripts/llm_baseline.py [--scenario ID] [--cap N] [--export DIR]
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from cascadeguard.agents.cache import DEFAULT_CACHE_DIR, DecisionCache
from cascadeguard.agents.llm import CappedClient, LLMConfig, llm_agents, make_client
from cascadeguard.cli import baseline_markdown, load_world
from cascadeguard.engine.constraints import Reason
from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.storage.export import run_export, write_exports

CITATION_REASONS = {
    Reason.UNKNOWN_CITATION.value,
    Reason.DRAFT_CITATION.value,
    Reason.CITATION_OUT_OF_SCOPE.value,
}


def compare(llm: RunResult, scripted: RunResult) -> list[str]:
    lines: list[str] = []
    lf, sf = {f.id for f in llm.failures}, {f.id for f in scripted.failures}
    lines.append(f"Diagnosed failures: LLM {len(lf)}, scripted {len(sf)}")
    for fid in sorted(lf & sf):
        lines.append(f"  both:          {fid}")
    for fid in sorted(sf - lf):
        lines.append(f"  scripted only: {fid}")
    for fid in sorted(lf - sf):
        lines.append(f"  LLM only:      {fid}")
    lines.append("Recovery goals (LLM | scripted):")
    for (goal, lm), (_, sm) in zip(llm.goals, scripted.goals, strict=True):

        def show(m: int | None) -> str:
            return f"met at T+{m}" if m is not None else "unmet"

        lines.append(f"  {goal}: {show(lm)} | {show(sm)}")

    def accepted(r: RunResult) -> set[tuple[int, str, str]]:
        return {
            (e.minute, e.role or "", e.action or "")
            for e in r.log
            if e.kind == "accepted" and e.action is not None
        }

    la, sa = accepted(llm), accepted(scripted)
    lines.append(f"Accepted actions: LLM {len(la)}, scripted {len(sa)}, in common {len(la & sa)}")
    for m, role, action in sorted(la - sa):
        lines.append(f"  LLM only:      T+{m:02d} {role} {action}")
    for m, role, action in sorted(sa - la):
        lines.append(f"  scripted only: T+{m:02d} {role} {action}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="uae_health_access")
    parser.add_argument("--cap", type=int, default=72)
    parser.add_argument("--export", type=Path, default=PROJECT_ROOT / "data" / "llm_baseline")
    args = parser.parse_args()

    config = LLMConfig.from_env()
    scripted_world = load_world(args.scenario)
    roles = tuple(r.id for r in scripted_world.roles.roles)
    cache = DecisionCache(DEFAULT_CACHE_DIR)
    paced = make_client(config, cap=args.cap)
    client: CappedClient = paced.inner
    agents = llm_agents(roles, cache, config=config, client=paced)
    label = (
        f"LLM agents (model from CASCADEGUARD_MODEL; output mode {config.output_mode}; "
        f"live calls through the decision cache, capped at {args.cap} requests)"
    )
    world = replace(scripted_world, agents=dict(agents), agent_label=label, cache=cache)
    result = world.baseline()
    scripted = scripted_world.baseline()

    no_decision = [f for f in result.findings if f.kind == Reason.NO_DECISION.value]
    reasons: dict[str, int] = {}
    for f in no_decision:
        reason = f.detail.rsplit("(", 1)[-1].rstrip(")")
        reasons[reason] = reasons.get(reason, 0) + 1
    rejected = [f for f in result.findings if f.kind in CITATION_REASONS]
    steps = len(result.views)
    print(f"LLM baseline: {args.scenario}")
    print(f"Agents: {label}")
    print(f"Requests sent: {client.requests} of {args.cap} (refused at the cap: {client.refused})")
    print(f"Steps completed with a decision: {steps - len(no_decision)} of {steps}")
    print(f"  cache: {cache.stats.hits} reused, {cache.stats.misses} asked")
    print(f"no_decision findings: {len(no_decision)} {reasons or ''}")
    if client.errors:
        print(f"Request errors: {sorted(set(client.errors))}")
    print(f"Rejected citations: {len(rejected)}")
    for f in rejected:
        print(f"  T+{f.minute:02d} {f.role}: {f.kind} {list(f.clause_ids)}")
    other = sorted(
        {f.kind for f in result.findings} - CITATION_REASONS - {Reason.NO_DECISION.value}
    )
    print(f"Other finding kinds: {other}")
    print(f"Tokens: {client.prompt_tokens} input, {client.completion_tokens} output")
    missing = f" ({client.cost_missing} responses without cost)" if client.cost_missing else ""
    print(f"Total cost (OpenRouter usage): {client.cost:.6f} credits (USD){missing}")
    print(f"Time in API calls: {client.seconds:.1f} s")
    print("")
    print("\n".join(compare(result, scripted)))
    for path in write_exports(
        args.export,
        f"{args.scenario}-llm-baseline",
        run_export(result),
        baseline_markdown(args.scenario, result, None),
    ):
        shown = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        print(f"exported {shown.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
