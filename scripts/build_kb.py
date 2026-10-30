"""Build the vector knowledge base into policies/kb/ (see cascadeguard.knowledge.kb).

Chunks the keyword search's corpus (extracted text outside NOT_SEARCHED and the books, plus the
reviewed, pinned transcriptions) and embeds each chunk with the free NVIDIA Nemotron 3.5 Embed
1B model through OpenRouter (OPENROUTER_API_KEY and OPENROUTER_BASE_URL from .env; nothing runs
locally). Writes chunks.jsonl, vectors.npy (1,024 dimensions, renormalised) and manifest.json.

`--sample N` embeds only the first N chunks, reports time and result, and writes nothing.

Usage: uv run python scripts/build_kb.py [--sample N]
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
    write_index,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the vector knowledge base.")
    parser.add_argument("--sample", type=int, help="embed only the first N chunks; write nothing")
    args = parser.parse_args()

    chunks = build_chunks()
    texts = [c.text for c in chunks][: args.sample] if args.sample else [c.text for c in chunks]
    print(f"{len(chunks)} chunks in the corpus; embedding {len(texts)} in batches of {BATCH}")
    try:
        embedder = OpenRouterEmbedder()
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
