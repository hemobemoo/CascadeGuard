"""Embed the adviser's preset questions once into policies/kb/adviser_query_vectors.json.

The preset questions (scenarios/<id>/adviser_questions.yaml) are embedded with the knowledge
base's own model (policies/kb/manifest.json; `kb.MODEL_SLUG`, checked against the manifest when
the index loads) and stored with the index digest, so a preset retrieves the same context with no
API key. Gate 4: this sends requests to OpenRouter. Without `--run` it is a dry run that only
prints how many texts and requests it would send.

Usage: uv run python scripts/embed_adviser_presets.py [--scenario ID] [--run]
"""

import argparse
import math

from cascadeguard.agents.adviser_query import PRESET_VECTORS, load_presets
from cascadeguard.knowledge.kb import (
    BATCH,
    KB_DIR,
    MODEL_SLUG,
    KnowledgeBaseError,
    OpenRouterEmbedder,
    load_index,
    write_vectors,
)
from cascadeguard.simulation.loader import SCENARIOS_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed the adviser's preset questions.")
    parser.add_argument("--scenario", default="uae_health_access")
    parser.add_argument("--run", action="store_true", help="send the requests (gate 4)")
    args = parser.parse_args()
    texts = [text for _, text in load_presets(SCENARIOS_DIR / args.scenario)]
    requests = math.ceil(len(texts) / BATCH)
    print(f"{len(texts)} preset questions, {requests} embedding request(s) with {MODEL_SLUG}")
    if not args.run:
        print("dry run: nothing sent (add --run after the human's approval, gate 4)")
        return 0
    try:
        digest = load_index().digest
        embedder = OpenRouterEmbedder()
        count = write_vectors(embedder, texts, digest, KB_DIR / PRESET_VECTORS)
    except KnowledgeBaseError as exc:
        print(f"embed_adviser_presets: {exc}")
        return 2
    print(
        f"{count} questions embedded into policies/kb/{PRESET_VECTORS}, "
        f"{embedder.requests} requests"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
