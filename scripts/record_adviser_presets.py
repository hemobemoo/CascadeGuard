"""Record the LLM answers to the adviser's preset questions, for offline replay in the demo.

Each preset (scenarios/<id>/adviser_questions.yaml) is asked at its own step through
`agents.adviser_query.ask` with the configured chat model (.env), on keyword retrieval (no query
embedding: the preset embedding failed, human decision 2026-11-06), with a fresh client capped
at `REQUEST_CAP` requests per question. Answers go to docs/evaluation/adviser/cache/; replay with
`cascadeguard ask <scenario> --at T+n "<preset>" --cache docs/evaluation/adviser/cache`.

Gate 4: this sends requests to OpenRouter. Without `--run` it is a dry run that prints the plan.

Usage: uv run python scripts/record_adviser_presets.py [--scenario ID] [--run]
"""

import argparse
from pathlib import Path

from cascadeguard.agents import adviser_query as aq
from cascadeguard.agents.llm import CappedClient, LLMConfig, make_client
from cascadeguard.cli import adviser_view, load_world
from cascadeguard.knowledge.kb import committed_index
from cascadeguard.simulation.loader import PROJECT_ROOT, SCENARIOS_DIR

CACHE = PROJECT_ROOT / "docs" / "evaluation" / "adviser" / "cache"


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the adviser's preset answers.")
    parser.add_argument("--scenario", default="uae_health_access")
    parser.add_argument("--run", action="store_true", help="send the requests (gate 4)")
    args = parser.parse_args()
    presets = aq.load_presets(SCENARIOS_DIR / args.scenario)
    print(
        f"{len(presets)} preset questions, at most {aq.REQUEST_CAP} chat requests each "
        f"({len(presets) * aq.REQUEST_CAP} at most), keyword retrieval, cache {_rel(CACHE)}"
    )
    if not args.run:
        print("dry run: nothing sent (add --run after the human's approval, gate 4)")
        return 0
    config = LLMConfig.from_env()
    world = load_world(args.scenario)
    roles = [r.id for r in world.roles.roles]
    texts = [t for _, t in presets]
    index = committed_index()
    total = 0
    for at, text in presets:
        client = make_client(config, cap=aq.REQUEST_CAP)
        asker = aq.Asker(
            config=config,
            client=client,
            cache=aq.AnswerCache(CACHE),
            index=index,
            output_mode=config.output_mode,
        )
        answer = aq.ask(
            args.scenario, text, adviser_view(world, at), world.clauses, roles, asker, texts
        )
        inner = client.inner
        sent = inner.requests if isinstance(inner, CappedClient) else 0
        total += sent
        print(f"T+{at:02d} [{sent} requests] {answer.mode_detail} | {text[:60]}")
    print(f"{total} chat requests in all")
    return 0


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
