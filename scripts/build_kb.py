"""Build the vector knowledge base into policies/kb/ (see cascadeguard.knowledge.kb).

Chunks the keyword search's corpus (extracted text outside NOT_SEARCHED and the books, plus the
reviewed, pinned transcriptions) and embeds each chunk with the free NVIDIA Nemotron 3.5 Embed
1B model through OpenRouter (OPENROUTER_API_KEY and OPENROUTER_BASE_URL from .env; nothing runs
locally). Writes chunks.jsonl, vectors.npy (1,024 dimensions, renormalised) and manifest.json,
then embeds the queries in policies/kb/acceptance.json into query_vectors.json, so the
acceptance tests run with no API.

`--sample N` embeds only the first N chunks, reports time and result, and writes nothing.
`--queries-only` re-embeds only the acceptance queries (the index must be current).

Usage: uv run python scripts/build_kb.py [--sample N | --queries-only]
"""

import argparse
import time
from datetime import date

import numpy as np

from cascadeguard.knowledge.kb import (
    BATCH,
    DIMENSIONS,
    KB_DIR,
    KnowledgeBaseError,
    OpenRouterEmbedder,
    build_chunks,
    load_index,
    write_index,
    write_query_vectors,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the vector knowledge base.")
    parser.add_argument("--sample", type=int, help="embed only the first N chunks; write nothing")
    parser.add_argument("--queries-only", action="store_true", help="re-embed acceptance queries")
    args = parser.parse_args()

    try:
        embedder = OpenRouterEmbedder()
        if args.queries_only:
            count = write_query_vectors(embedder, load_index().digest, KB_DIR)
            print(f"{count} acceptance queries embedded, {embedder.requests} requests")
            return 0
        chunks = build_chunks()
        texts = [c.text for c in chunks][: args.sample] if args.sample else [c.text for c in chunks]
        print(f"{len(chunks)} chunks in the corpus; embedding {len(texts)} in batches of {BATCH}")
        started = time.perf_counter()
        vectors = embedder.documents(texts)
        elapsed = time.perf_counter() - started
    except KnowledgeBaseError as exc:
        print(f"build_kb: {exc}")
        return 2
    norms = np.linalg.norm(vectors, axis=1)
    print(
        f"{vectors.shape[0]} vectors x {vectors.shape[1]} dimensions in {elapsed:.1f} s, "
        f"{embedder.requests} requests; norms {norms.min():.4f}-{norms.max():.4f}"
    )
    if args.sample:
        similarity = vectors @ vectors.T
        np.fill_diagonal(similarity, np.nan)
        print(
            f"pairwise cosine among the sample: {np.nanmin(similarity):.3f} to "
            f"{np.nanmax(similarity):.3f} (mean {np.nanmean(similarity):.3f}); nothing written"
        )
        return 0
    assert vectors.shape == (len(chunks), DIMENSIONS)
    digest = write_index(chunks, vectors, date.today().isoformat(), KB_DIR)
    mapped = sum(1 for c in chunks if c.clauses)
    print(f"{mapped} chunks hold a reviewed clause; index digest {digest} -> {KB_DIR}")
    try:
        count = write_query_vectors(embedder, digest, KB_DIR)
    except KnowledgeBaseError as exc:
        print(f"build_kb: index written, but the acceptance queries failed: {exc}")
        return 2
    print(f"{count} acceptance queries embedded into query_vectors.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
