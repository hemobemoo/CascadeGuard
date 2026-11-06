"""Embed the retrieval-evaluation queries and the adviser's preset questions in ONE request.

Gate 4 (human, 2026-11-06): one embedding request (up to 4 with the automatic retries), with the
knowledge base's own model (`kb.MODEL_SLUG`, policies/kb/manifest.json) and no other. Writes:
- tests/evaluation/kb_query_vectors.json: the queries of tests/evaluation/kb_queries.yaml, read
  by scripts/kb_retrieval_eval.py and its test with no API;
- policies/kb/adviser_query_vectors.pending.json: the six preset questions. Nothing reads this
  file: the adviser reads only `adviser_query_vectors.json` (PRESET_VECTORS), so the preset cache
  keys, the recorded answers and the report stay unchanged (human, 2026-11-06).
Both files are tied to the index digest and the model, in the `kb.write_vectors` format.

Without `--run` it is a dry run that prints the texts and request count and sends nothing.

Usage: uv run python scripts/embed_eval_queries.py [--run]
"""

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path

import yaml

from cascadeguard.agents.adviser_query import load_presets
from cascadeguard.knowledge.kb import (
    BATCH,
    KB_DIR,
    MODEL_SLUG,
    QUERY_PREFIX,
    KnowledgeBaseError,
    OpenRouterEmbedder,
    Vectors,
    load_index,
)
from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.simulation.loader import SCENARIOS_DIR

EVAL_DIR = PROJECT_ROOT / "tests" / "evaluation"
QUERIES = EVAL_DIR / "kb_queries.yaml"
EVAL_VECTORS = "kb_query_vectors.json"
PENDING_PRESETS = "adviser_query_vectors.pending.json"


def eval_queries() -> list[str]:
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    return [str(q["query"]) for q in data["queries"]]


def write(path: Path, texts: Sequence[str], vectors: Vectors, digest: str) -> None:
    data = {
        "index_digest": digest,
        "model_slug": MODEL_SLUG,
        "query_prefix": QUERY_PREFIX,
        "vectors": {t: [float(x) for x in v] for t, v in zip(texts, vectors, strict=True)},
    }
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed the evaluation queries and presets.")
    parser.add_argument("--run", action="store_true", help="send the one request (gate 4)")
    args = parser.parse_args()
    queries = eval_queries()
    presets = [text for _, text in load_presets(SCENARIOS_DIR / "uae_health_access")]
    texts = queries + presets
    if len(set(texts)) != len(texts):
        print("embed_eval_queries: a text appears twice; refusing")
        return 2
    requests = math.ceil(len(texts) / BATCH)
    print(
        f"{len(queries)} queries + {len(presets)} presets = {len(texts)} texts, "
        f"{requests} request(s) with {MODEL_SLUG}"
    )
    if requests != 1:
        print("embed_eval_queries: more than one request; the approval is for one. Refusing.")
        return 2
    if not args.run:
        print("dry run: nothing sent (add --run after the human's approval, gate 4)")
        return 0
    try:
        digest = load_index().digest
        embedder = OpenRouterEmbedder()
        vectors = embedder.queries(texts)
    except KnowledgeBaseError as exc:
        print(f"embed_eval_queries: {exc}")
        return 2
    write(EVAL_DIR / EVAL_VECTORS, queries, vectors[: len(queries)], digest)
    write(KB_DIR / PENDING_PRESETS, presets, vectors[len(queries) :], digest)
    print(
        f"wrote tests/evaluation/{EVAL_VECTORS} and policies/kb/{PENDING_PRESETS}; "
        f"{embedder.requests} request(s) sent, retries included"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
