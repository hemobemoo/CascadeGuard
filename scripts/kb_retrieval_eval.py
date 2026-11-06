"""Retrieval evaluation of the knowledge base (Task 4): Precision@3, Recall@5 and MRR@10 of the
committed hybrid search over the queries in tests/evaluation/kb_queries.yaml.

No API: the query vectors were embedded once (scripts/embed_eval_queries.py, gate 4) into
tests/evaluation/kb_query_vectors.json and are read back with `kb.StoredQueries`. The search is
`kb.search_kb` exactly as committed (no ranking change). The relevance rule and the metric
definitions are the ones fixed in the header of kb_queries.yaml before any search was run.
Writes docs/evaluation/kb-retrieval.md; `--check` (and tests/unit/test_kb_retrieval_eval.py)
keeps it current.

    uv run python scripts/kb_retrieval_eval.py [--check]
"""

import argparse
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np
import yaml

from cascadeguard.knowledge.kb import (
    MAX_PER_SOURCE,
    MODEL_SLUG,
    RRF_K,
    SCORE_DECIMALS,
    Hit,
    Index,
    StoredQueries,
    Vectors,
    load_index,
    search_kb,
    shared_ranks,
)
from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.knowledge.retrieval import keyword_score, query_words

EVAL_DIR = PROJECT_ROOT / "tests" / "evaluation"
QUERIES = EVAL_DIR / "kb_queries.yaml"
VECTORS = "kb_query_vectors.json"
OUTPUT = PROJECT_ROOT / "docs" / "evaluation" / "kb-retrieval.md"
K = 10
QUERIES_COMMIT = "9e8517f"  # kb_queries.yaml committed before any embedding or search
VECTORS_COMMIT = "783be71"  # the one embedding request's vectors, committed before any search

Page = tuple[str, int]


def short(source: str) -> str:
    name = source.removeprefix("ocr/").removeprefix("web/").removesuffix(".pdf")
    return name if len(name) <= 38 else name[:37] + "…"


def locations(hit: Hit) -> set[Page]:
    """The hit's page and the pages of its exact copies (`Chunk.also_in`)."""
    pages = {(hit.chunk.source_file, hit.chunk.page)}
    for chunk_id in hit.chunk.also_in:
        source, rest = chunk_id.split("#p", 1)
        pages.add((source, int(rest.split("#c", 1)[0])))
    return pages


@dataclass(frozen=True)
class Scored:
    query: dict[str, Any]
    relevant: frozenset[Page]
    hits: tuple[Hit, ...]
    flags: tuple[bool, ...]  # per hit: relevant?
    ceiling: float  # best Precision@3 the per-source cap allows

    @property
    def first(self) -> int | None:
        return next((i + 1 for i, f in enumerate(self.flags) if f), None)

    @property
    def p3(self) -> float:
        return sum(self.flags[:3]) / 3

    @property
    def r5(self) -> float:
        found: set[Page] = set()
        for h in self.hits[:5]:
            found |= locations(h)
        return len(found & self.relevant) / len(self.relevant)

    @property
    def rr(self) -> float:
        return 1 / self.first if self.first else 0.0


def relevant_pages(q: dict[str, Any]) -> frozenset[Page]:
    pages = {(str(q["expect_source"]), int(q["expect_page"]))}
    pages |= {(str(a["source"]), int(a["page"])) for a in q.get("also_relevant", [])}
    return frozenset(pages)


def ceiling(index: Index, relevant: frozenset[Page]) -> float:
    """Best possible Precision@3: relevant ranked chunks, at most MAX_PER_SOURCE per document."""
    per_source: dict[str, int] = {}
    for c in index.chunks:
        if c.duplicate_of is None and (c.source_file, c.page) in relevant:
            per_source[c.source_file] = per_source.get(c.source_file, 0) + 1
    return min(3, sum(min(MAX_PER_SOURCE, n) for n in per_source.values())) / 3


def similarities(index: Index, embedder: StoredQueries, query: str) -> Vectors:
    """Cosine of the stored query vector (L2-normalised, as `search_kb` does) to every chunk."""
    q: Vectors = embedder.query(query)[0]
    return (index.vectors @ (q / np.linalg.norm(q))).astype(np.float32)


def cosine(index: Index, embedder: StoredQueries, query: str, hit: Hit) -> float:
    row = next(i for i, c in enumerate(index.chunks) if c.id == hit.chunk.id)
    return round(float(similarities(index, embedder, query)[row]), SCORE_DECIMALS)


def half_ranks(
    index: Index, embedder: StoredQueries, query: str, relevant: frozenset[Page]
) -> tuple[int, int | None, int]:
    """Diagnostic only, the search unchanged: the best rank a relevant chunk gets in each half
    of `search_kb` on its own (vector, keyword), computed the same way (rounded cosine, keyword
    score, shared ranks over unduplicated chunks), before fusion and the per-document cap."""
    ranked = [i for i, c in enumerate(index.chunks) if c.duplicate_of is None]
    cos = similarities(index, embedder, query)
    vector = shared_ranks({i: round(float(cos[i]), SCORE_DECIMALS) for i in ranked})
    words = query_words(query)
    scores = {i: float(keyword_score(index.chunks[i].text, words)) for i in ranked}
    keyword = shared_ranks({i: x for i, x in scores.items() if x})
    rel = [
        i
        for i in ranked
        if (index.chunks[i].source_file, index.chunks[i].page) in relevant
        or any(c.startswith(f"{s}#p{p}#") for s, p in relevant for c in index.chunks[i].also_in)
    ]
    best_kw = [keyword[i] for i in rel if i in keyword]
    fused = {i: 1 / (RRF_K + r) for i, r in vector.items()}
    for i, r in keyword.items():
        fused[i] += 1 / (RRF_K + r)
    uncapped = shared_ranks(fused)
    return (
        min(vector[i] for i in rel),
        min(best_kw) if best_kw else None,
        min(uncapped[i] for i in rel),
    )


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def render() -> str:
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    index = load_index()
    embedder = StoredQueries(index.digest, kb_dir=EVAL_DIR, filename=VECTORS)
    scored: list[Scored] = []
    nothing: list[tuple[dict[str, Any], tuple[Hit, ...]]] = []
    for q in data["queries"]:
        hits = search_kb(str(q["query"]), k=K, index=index, embedder=embedder)
        if q.get("expect") == "nothing":
            nothing.append((q, hits))
            continue
        rel = relevant_pages(q)
        flags = tuple(bool(locations(h) & rel) for h in hits)
        scored.append(Scored(q, rel, hits, flags, ceiling(index, rel)))

    def row(label: str, group: list[Scored]) -> str:
        return (
            f"| {label} | {len(group)} | {mean([s.p3 for s in group]):.3f} "
            f"| {mean([s.ceiling for s in group]):.3f} | {mean([s.r5 for s in group]):.3f} "
            f"| {mean([s.rr for s in group]):.3f} |"
        )

    topics: dict[str, list[Scored]] = {}
    for s in scored:
        topics.setdefault(str(s.query["topic"]), []).append(s)
    lines = [
        "# Knowledge-base retrieval evaluation (generated)",
        "",
        "Generated by `uv run python scripts/kb_retrieval_eval.py` (Task 4); do not edit by hand.",
        f"Queries: `tests/evaluation/kb_queries.yaml`, {len(scored)} answerable and "
        f"{len(nothing)} that should find nothing, committed in {QUERIES_COMMIT} before any",
        "query was embedded or searched. Query vectors: one embedding request with the index's",
        f"own model (`{MODEL_SLUG}`; gate 4, human 2026-11-06), committed in {VECTORS_COMMIT}",
        "before any search; this report runs with no API. Search: `kb.search_kb` exactly as",
        f"committed (hybrid vector + keyword, reciprocal rank fusion, at most {MAX_PER_SOURCE}",
        f"chunks per document), k = {K}. No ranking change and no query rewording after seeing",
        "the results. The expected pages were chosen by the agent from the indexed text; one",
        "annotator, a small set: an indication, not a benchmark.",
        "",
        "Definitions (fixed in the query file before looking): a hit is relevant when its page,",
        "or a page of one of its exact copies, is the expected page or an `also_relevant` page.",
        "**Precision@3** = relevant hits in the top 3 / 3. **Recall@5** = distinct relevant",
        "pages in the top 5 / relevant pages. **MRR@10** = 1 / rank of the first relevant hit in",
        "the top 10, else 0. Averaged over the answerable queries. **P@3 ceiling** is the best",
        f"Precision@3 the per-document cap ({MAX_PER_SOURCE}) and the number of relevant chunks",
        "allow: most queries have one relevant page, so the ceiling is below 1.",
        "",
        "## Results",
        "",
        "| Queries | n | Precision@3 | P@3 ceiling | Recall@5 | MRR@10 |",
        "|---|---|---|---|---|---|",
        row("**All answerable**", scored),
        *(row(t, g) for t, g in topics.items()),
        "",
        "## Per query",
        "",
        "| Id | Expected (PDF page) | First relevant rank | P@3 | R@5 | Top 3 (source, page) |",
        "|---|---|---|---|---|---|",
    ]
    for s in scored:
        q = s.query
        expected = f"{short(str(q['expect_source']))} p.{q['expect_page']}"
        if q.get("also_relevant"):
            expected += " (+" + ", ".join(f"p.{a['page']}" for a in q["also_relevant"]) + ")"
        first = str(s.first) if s.first else f"miss (not in top {K})"
        top = "; ".join(
            f"{'**' if f else ''}{short(h.chunk.source_file)} p.{h.chunk.page}{'**' if f else ''}"
            for h, f in zip(s.hits[:3], s.flags[:3], strict=True)
        )
        lines.append(f"| {q['id']} | {expected} | {first} | {s.p3:.2f} | {s.r5:.2f} | {top} |")
    lines += [
        "",
        "Relevant hits are in bold.",
        "",
        "## Diagnosis: each half of the search on its own",
        "",
        "Diagnostic only; the search is unchanged. For each answerable query, the best rank a",
        "relevant chunk gets in the vector ranking alone and in the keyword ranking alone (shared",
        "ranks over all unduplicated chunks, before fusion and before the per-document cap), next",
        "to the fused rank before the cap (the same RRF sum over every chunk) and the fused",
        "rank the search returns (after the cap). A relevant chunk that is fused-ranked high but",
        "missing after the cap was displaced by two better-fused chunks of the same document.",
        "",
        "| Id | Vector-only rank | Keyword-only rank | Fused, before the cap | Fused, returned |",
        "|---|---|---|---|---|",
    ]
    vector_first = capped = diluted = 0
    for s in scored:
        vr, kr, ur = half_ranks(index, embedder, str(s.query["query"]), s.relevant)
        vector_first += vr == 1
        missed = not s.first or s.first > 5
        capped += missed and ur <= 10
        diluted += missed and ur > 10
        fused = str(s.first) if s.first else f"not in top {K}"
        kw = str(kr) if kr is not None else "- (no query word)"
        lines.append(f"| {s.query['id']} | {vr} | {kw} | {ur} | {fused} |")
    lines += [
        "",
        f"The vector ranking alone puts a relevant chunk first for {vector_first} of "
        f"{len(scored)} answerable queries. Of the {capped + diluted} misses (no relevant hit in "
        f"the top 5): {capped} have a relevant chunk in the fused top 10 before the cap, so the",
        "per-document cap removed it; the other "
        f"{diluted} have a relevant chunk the vector half ranks high but",
        "the keyword half ranks far down, so the fusion places it below the 10th.",
        "",
        "## Misses",
        "",
    ]
    misses = [s for s in scored if not s.first or s.first > 5]
    if not misses:
        lines.append("None: every answerable query has a relevant hit in the top 5.")
    for s in misses:
        where = f"first relevant hit at rank {s.first}" if s.first else f"not in the top {K}"
        lines.append(f'- **{s.query["id"]}** ({s.query["topic"]}): "{s.query["query"]}"; {where}.')
    lines += [
        "",
        "## Queries that should find nothing",
        "",
        "Outside the corpus. Not scored; the top 5 hits are reported as they are. No relevance",
        "threshold was set: the search always returns k chunks, so these show what a",
        "nothing-to-find query gets. Fused = RRF score; cosine = similarity of the query vector",
        "to the chunk (rounded to 4 decimals, as the search does); keyword rank `-` = no query",
        "word in the chunk.",
        "",
    ]
    for q, hits in nothing:
        lines += [
            f'**{q["id"]}**: "{q["query"]}"',
            "",
            "| Rank | Source, page | Fused | Cosine | Vector rank | Keyword rank |",
            "|---|---|---|---|---|---|",
        ]
        for i, h in enumerate(hits[:5], 1):
            kw = str(h.keyword_rank) if h.keyword_rank is not None else "-"
            lines.append(
                f"| {i} | {short(h.chunk.source_file)} p.{h.chunk.page} | {h.score:.4f} "
                f"| {cosine(index, embedder, str(q['query']), h):.4f} | {h.vector_rank} | {kw} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the KB retrieval evaluation.")
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{OUTPUT.relative_to(PROJECT_ROOT)} is stale: run scripts/kb_retrieval_eval.py")
            return 1
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
