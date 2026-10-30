"""Vector knowledge base: the keyword search's corpus (`retrieval.searchable_pages`), chunked
per page and embedded with NVIDIA Nemotron 3.5 Embed 1B through OpenRouter's embeddings API,
for the LLM context path only. Nothing is downloaded or run locally.

Chunks are context only and never citable, exactly like keyword snippets: each carries the
snippet label of its page. A chunk that holds the quote of a reviewed clause lists that clause
with the clause's own `status_label`; nothing is shown as binding unless that label says so.

The index is built offline (`scripts/build_kb.py`) into policies/kb/: chunks.jsonl, vectors.npy
(rows in chunk order) and manifest.json (model slug, dimensions, prefix rule, chunk settings,
build date, digest). Loading it re-chunks the current corpus and refuses an index that no longer
matches, so the index follows the same page rules as the search, including the runtime pin
check on reviewed transcriptions. The digest (`index_digest`) is computed from the chunks, the
model slug, the dimensions, the prefix rule and the chunk settings, never from the vectors: API
vectors can differ slightly between calls, and that must not change the `+kb:` prompt version
or the LLM cache keys. The build date is recorded but is not part of the digest.

Search is exact cosine similarity over the committed vectors (numpy; no vector database at
about 1,250 chunks), scores rounded to SCORE_DECIMALS and ties broken by chunk id, so the order
does not depend on the last bits of a query embedding. Only the query is embedded at search
time; that needs OPENROUTER_API_KEY and OPENROUTER_BASE_URL (.env) and the network, and fails
with a clear message without them. The scripted demo and the keyword path never touch it.
`export_kb_main` writes the chunks in a ChromaDB-compatible form the reference code below loads
into its `kb_main` collection.

Model (checked 2026-10-30). OpenRouter's embeddings catalogue lists
`nvidia/nemotron-3.5-embed-1b:free` (canonical slug nvidia/nemotron-3.5-embed-1b-20261021,
free, 32,768-token context) with no
supported request parameters, so neither `dimensions` nor `input_type` can be sent. NVIDIA's
model card (huggingface.co/nvidia/Nemotron-3.5-Embed-1B-BF16):
- Prefixes: retrieval uses "query:" for queries and "passage:" for documents (applied as the
  chat system role by its processor; "Use `query:` for text queries and `passage:` for
  documents" for vLLM offline). OpenRouter documents no prefix handling, so QUERY_PREFIX and
  DOCUMENT_PREFIX are prepended to the text here. Whether the provider also applies them is not
  documented (not checked).
- Dimensions: 2,048, mean-pooled and L2-normalised; the card says the vector may be truncated
  from the end (e.g. to the first 1,024) "provided they are L2-normalized after truncation".
  So vectors are cut to DIMENSIONS and renormalised here.

Adapted from the ITU AI Readiness simulation's ingestion (github.com/CrashingGuru/ITUAIReadiness,
simulation/server/knowledge/ingest.py and kb.py at 84010da; MIT License, Copyright (c) 2026
Vishnu Ram OV): the 256-word chunks with a 30-word overlap, the merge of a short tail into the
previous chunk, the 2,000-character cap, and the `kb_main` collection with cosine distance and
pre-computed embeddings (the export). Changed here: chunks never cross a page and keep their
character span; the input is our extracted records, not re-parsed PDFs; chunk ids are fixed,
not random; no ingestion timestamp per chunk; no source type or country guessed from file names.
"""

import hashlib
import json
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from cascadeguard.domain.policies import ClauseStatus, PolicyClause
from cascadeguard.knowledge.loader import (
    APPROVALS_FILE,
    EXTRACTED_DIR,
    PROJECT_ROOT,
    TRANSCRIPTIONS_DIR,
    load_engine_clauses,
    quote_span,
)
from cascadeguard.knowledge.retrieval import searchable_pages

KB_DIR = PROJECT_ROOT / "policies" / "kb"
MODEL_SLUG = "nvidia/nemotron-3.5-embed-1b:free"  # chosen by the human (PR 3, 2026-10-30)
NATIVE_DIMENSIONS = 2048
DIMENSIONS = 1024  # truncated from the end, then L2-normalised (model card)
DOCUMENT_PREFIX = "passage: "
QUERY_PREFIX = "query: "
PREFIX_RULE = f"text prefixed client-side: documents {DOCUMENT_PREFIX!r}, queries {QUERY_PREFIX!r}"
BATCH = 32  # chunks per request
RETRIES = 3  # after the first attempt
EMBED_ENV = ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL")
# Chunk settings of the reference code (config.py: chunk_size, chunk_overlap; ingest.py).
CHUNK_WORDS = 256
OVERLAP_WORDS = 30
MIN_TAIL_WORDS = 20  # a tail of this many new words or fewer joins the previous chunk
MAX_CHARS = 2000
REQUEST_TIMEOUT_SECONDS = 120.0
SCORE_DECIMALS = 4
COLLECTION = "kb_main"  # the reference code's collection
_WORD = re.compile(r"\S+")

Vectors = npt.NDArray[np.float32]


class KnowledgeBaseError(RuntimeError):
    """The committed index does not match the corpus or its manifest, or the embedding API
    is not configured or not reachable. The message names variables, never values."""


@dataclass(frozen=True, slots=True)
class ClauseRef:
    id: str
    status_label: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str  # "<source_file>#p<page>#c<n>"
    source_file: str
    page: int
    start: int  # character span in the page text
    end: int
    label: str  # the page's snippet label: context only, never citable
    text: str  # the span's words joined by single spaces
    clauses: tuple[ClauseRef, ...] = ()  # reviewed clauses whose quote overlaps the span

    def record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_file": self.source_file,
            "page": self.page,
            "start": self.start,
            "end": self.end,
            "label": self.label,
            "text": self.text,
            "clauses": [{"id": c.id, "status_label": c.status_label} for c in self.clauses],
        }

    @staticmethod
    def from_record(r: dict[str, Any]) -> "Chunk":
        clauses = tuple(ClauseRef(str(c["id"]), str(c["status_label"])) for c in r["clauses"])
        return Chunk(
            str(r["id"]),
            str(r["source_file"]),
            int(r["page"]),
            int(r["start"]),
            int(r["end"]),
            str(r["label"]),
            str(r["text"]),
            clauses,
        )


@dataclass(frozen=True, slots=True)
class Hit:
    score: float
    chunk: Chunk


def _windows(n_words: int) -> list[tuple[int, int]]:
    """Word windows of one page: CHUNK_WORDS long, OVERLAP_WORDS shared with the previous one,
    and a last window adding MIN_TAIL_WORDS new words or fewer merged into the one before."""
    if n_words == 0:
        return []
    windows = [(0, min(CHUNK_WORDS, n_words))]
    while windows[-1][1] < n_words:
        start = windows[-1][1] - OVERLAP_WORDS
        windows.append((start, min(start + CHUNK_WORDS, n_words)))
    if len(windows) > 1 and windows[-1][1] - windows[-2][1] <= MIN_TAIL_WORDS:
        windows[-2:] = [(windows[-2][0], n_words)]
    return windows


def _capped(words: Sequence[re.Match[str]], a: int, b: int) -> list[tuple[int, int]]:
    """Split a window in halves by word count until each joined text fits MAX_CHARS."""
    text_len = sum(len(w.group()) for w in words[a:b]) + (b - a - 1)
    if text_len <= MAX_CHARS or b - a == 1:
        return [(a, b)]
    middle = (a + b) // 2
    return _capped(words, a, middle) + _capped(words, middle, b)


def chunk_page(source_file: str, page: int, text: str, label: str) -> list[Chunk]:
    words = list(_WORD.finditer(text))
    spans = [s for a, b in _windows(len(words)) for s in _capped(words, a, b)]
    return [
        Chunk(
            id=f"{source_file}#p{page}#c{n}",
            source_file=source_file,
            page=page,
            start=words[a].start(),
            end=words[b - 1].end(),
            label=label,
            text=" ".join(w.group() for w in words[a:b]),
        )
        for n, (a, b) in enumerate(spans)
    ]


def _clause_refs(
    chunks: list[Chunk],
    clauses: Iterable[PolicyClause],
    extracted_dir: Path,
    transcriptions_dir: Path,
) -> list[Chunk]:
    """Attach each reviewed clause to the chunks of its own page whose span overlaps its quote.
    Drafts and illustrative clauses are never attached."""
    by_page: dict[tuple[str, int], list[ClauseRef]] = {}
    spans: dict[str, tuple[int, int]] = {}
    for clause in sorted(clauses, key=lambda c: c.id):
        if clause.status is not ClauseStatus.REVIEWED or clause.page is None:
            continue
        span = quote_span(clause, extracted_dir, transcriptions_dir)
        if span is None or clause.source_file is None:
            continue
        spans[clause.id] = span
        ref = ClauseRef(clause.id, clause.status_label)
        by_page.setdefault((clause.source_file, clause.page), []).append(ref)
    out: list[Chunk] = []
    for chunk in chunks:
        refs = tuple(
            ref
            for ref in by_page.get((chunk.source_file, chunk.page), [])
            if spans[ref.id][0] < chunk.end and chunk.start < spans[ref.id][1]
        )
        out.append(replace(chunk, clauses=refs) if refs else chunk)
    return out


def build_chunks(
    extracted_dir: Path = EXTRACTED_DIR,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
    approvals_file: Path = APPROVALS_FILE,
    clauses: Iterable[PolicyClause] | None = None,
) -> list[Chunk]:
    """Chunks of every searchable page, in corpus order, with reviewed clauses attached."""
    chunks = [
        c
        for p in searchable_pages(extracted_dir, transcriptions_dir, approvals_file)
        for c in chunk_page(p.source_file, p.page, p.text, p.label)
    ]
    if len({c.id for c in chunks}) != len(chunks):
        raise KnowledgeBaseError("two searchable records share a source file and page")
    loaded = load_engine_clauses().values() if clauses is None else clauses
    return _clause_refs(chunks, loaded, extracted_dir, transcriptions_dir)


def settings() -> dict[str, Any]:
    """What the digest covers besides the chunks: model slug, dimensions, prefix rule, chunking."""
    return {
        "model_slug": MODEL_SLUG,
        "native_dimensions": NATIVE_DIMENSIONS,
        "dimensions": DIMENSIONS,
        "prefix_rule": PREFIX_RULE,
        "document_prefix": DOCUMENT_PREFIX,
        "query_prefix": QUERY_PREFIX,
        "chunk_words": CHUNK_WORDS,
        "overlap_words": OVERLAP_WORDS,
        "min_tail_words": MIN_TAIL_WORDS,
        "max_chars": MAX_CHARS,
    }


def digest_of(chunks: Sequence[Chunk]) -> str:
    """Digest of the chunks and `settings()`. Never of the vectors (module docstring)."""
    payload = {"settings": settings(), "chunks": [c.record() for c in chunks]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def write_index(
    chunks: Sequence[Chunk], vectors: Vectors, build_date: str, kb_dir: Path = KB_DIR
) -> str:
    if vectors.shape != (len(chunks), DIMENSIONS):
        raise KnowledgeBaseError(f"need one {DIMENSIONS}-dimension vector per chunk")
    kb_dir.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(c.record(), ensure_ascii=False) + "\n" for c in chunks)
    (kb_dir / "chunks.jsonl").write_text(lines, encoding="utf-8", newline="\n")
    np.save(kb_dir / "vectors.npy", _unit(vectors), allow_pickle=False)
    digest = digest_of(chunks)
    manifest = {
        **settings(),
        "build_date": build_date,
        "chunks": len(chunks),
        "digest": digest,
        "attribution": "chunking and kb_main layout adapted from CrashingGuru/ITUAIReadiness "
        "(MIT, Copyright (c) 2026 Vishnu Ram OV)",
    }
    text = json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    (kb_dir / "manifest.json").write_text(text, encoding="utf-8", newline="\n")
    return digest


@dataclass(frozen=True, slots=True)
class Index:
    chunks: tuple[Chunk, ...]
    vectors: Vectors  # unit rows, in chunk order
    manifest: dict[str, Any]

    @property
    def digest(self) -> str:
        return str(self.manifest["digest"])


def _read_chunks(kb_dir: Path) -> list[Chunk]:
    lines = (kb_dir / "chunks.jsonl").read_text("utf-8").splitlines()
    return [Chunk.from_record(json.loads(line)) for line in lines if line]


def load_index(
    kb_dir: Path = KB_DIR,
    extracted_dir: Path = EXTRACTED_DIR,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
    approvals_file: Path = APPROVALS_FILE,
) -> Index:
    """The committed index, refused unless its chunks equal the current corpus re-chunked
    (same page rules and runtime pin check as the search), its manifest matches the settings and
    its digest, and it has one vector per chunk."""
    if not (kb_dir / "manifest.json").exists():
        raise KnowledgeBaseError(f"no index in {kb_dir.name}/: run scripts/build_kb.py")
    manifest: dict[str, Any] = json.loads((kb_dir / "manifest.json").read_text("utf-8"))
    chunks = _read_chunks(kb_dir)
    if any(manifest.get(k) != v for k, v in settings().items()):
        raise KnowledgeBaseError("manifest settings differ from the code: rebuild the index")
    if digest_of(chunks) != manifest["digest"]:
        raise KnowledgeBaseError("chunks.jsonl does not match the manifest digest")
    if chunks != build_chunks(extracted_dir, transcriptions_dir, approvals_file):
        raise KnowledgeBaseError("the corpus changed since the index was built: rebuild it")
    vectors: Vectors = np.load(kb_dir / "vectors.npy", allow_pickle=False).astype(np.float32)
    if vectors.shape != (len(chunks), DIMENSIONS):
        raise KnowledgeBaseError("vectors.npy does not have one row per chunk")
    return Index(tuple(chunks), _unit(vectors), manifest)


@cache
def committed_index() -> Index:
    return load_index()


def index_digest() -> str:
    """Digest of the committed index, for the LLM prompt version (`+kb:<digest>`)."""
    return committed_index().digest


def _unit(vectors: Vectors) -> Vectors:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return (vectors / np.where(norms == 0, 1, norms)).astype(np.float32)


class Embedder(Protocol):
    def documents(self, texts: Sequence[str]) -> Vectors: ...

    def query(self, text: str) -> Vectors: ...


def truncate(vectors: Vectors) -> Vectors:
    """The first DIMENSIONS values of each vector, L2-normalised again (model card)."""
    return _unit(vectors[:, :DIMENSIONS])


class OpenRouterEmbedder:
    """MODEL_SLUG through OpenRouter's embeddings endpoint (the `openai` SDK with OpenRouter's
    base URL), BATCH texts per request, each request retried up to RETRIES times. The key comes
    from .env or the environment and never appears in a message."""

    def __init__(self, env_file: Path | None = None) -> None:
        from dotenv import dotenv_values
        from openai import OpenAI

        path = env_file or PROJECT_ROOT / ".env"
        values = {k: v for k, v in dotenv_values(path).items() if k in EMBED_ENV and v}
        values |= {k: os.environ[k] for k in EMBED_ENV if os.environ.get(k)}
        missing = [k for k in EMBED_ENV if not values.get(k, "").strip()]
        if missing:
            raise KnowledgeBaseError(
                f"the knowledge base embeds queries through OpenRouter and needs "
                f"{', '.join(missing)} in .env (see .env.example); keyword context "
                "(--extracted-context) and the scripted demo need neither"
            )
        self._client = OpenAI(
            api_key=values["OPENROUTER_API_KEY"].strip(),
            base_url=values["OPENROUTER_BASE_URL"].strip(),
            max_retries=0,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        self.requests = 0

    def _embed(self, texts: Sequence[str]) -> Vectors:
        rows: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            rows.extend(self._request(list(texts[i : i + BATCH])))
        return truncate(np.array(rows, dtype=np.float32))

    def _request(self, batch: list[str]) -> list[list[float]]:
        problem = ""
        for _ in range(1 + RETRIES):
            self.requests += 1
            try:
                response = self._client.embeddings.create(model=MODEL_SLUG, input=batch)
            except Exception as exc:  # network, HTTP or decoding error: retried
                status = getattr(exc, "status_code", None)
                problem = type(exc).__name__ + (f" (HTTP {status})" if status else "")
                continue
            data = sorted(response.data, key=lambda d: d.index)
            vectors = [list(d.embedding) for d in data]
            if len(vectors) == len(batch) and all(len(v) >= DIMENSIONS for v in vectors):
                return vectors
            problem = f"{len(vectors)} vectors for {len(batch)} texts, or too few dimensions"
        raise KnowledgeBaseError(
            f"OpenRouter embeddings failed {1 + RETRIES} times for {MODEL_SLUG}: {problem}. "
            "Check the network and the key, then run again."
        )

    def documents(self, texts: Sequence[str]) -> Vectors:
        return self._embed([DOCUMENT_PREFIX + t for t in texts])

    def query(self, text: str) -> Vectors:
        return self._embed([QUERY_PREFIX + text])


@cache
def _embedder() -> OpenRouterEmbedder:
    return OpenRouterEmbedder()


def search_kb(
    query: str, k: int = 5, index: Index | None = None, embedder: Embedder | None = None
) -> tuple[Hit, ...]:
    """Top-k chunks by cosine similarity, rounded to SCORE_DECIMALS, ties broken by chunk id."""
    if not query.strip() or k <= 0:
        return ()
    embedder = embedder or _embedder()  # a missing key is reported first
    index = index or committed_index()
    vector = _unit(embedder.query(query))[0]
    raw: Vectors = index.vectors @ vector
    scores = [round(float(x), SCORE_DECIMALS) for x in raw]
    order = sorted(range(len(index.chunks)), key=lambda i: (-scores[i], index.chunks[i].id))
    return tuple(Hit(scores[i], index.chunks[i]) for i in order[:k])


def export_records(index: Index) -> list[dict[str, Any]]:
    """One record per chunk as the reference code's `KnowledgeBase.add_documents` takes it: id,
    document, embedding and metadata whose values are all strings (ChromaDB metadata takes no
    lists), using the reference's keys where they exist."""
    return [
        {
            "id": c.id,
            "document": c.text,
            "embedding": [float(x) for x in v],
            "metadata": {
                "source_file": c.source_file,
                "page": str(c.page),
                "span": f"{c.start}-{c.end}",
                "chunk_index": c.id.rsplit("#c", 1)[1],
                "label": c.label,
                "clause_ids": ",".join(r.id for r in c.clauses),
                "clause_labels": " | ".join(r.status_label for r in c.clauses),
                "document_category": "cascadeguard_policies",
            },
        }
        for c, v in zip(index.chunks, index.vectors, strict=True)
    ]


def export_kb_main(path: Path, index: Index | None = None) -> int:
    records = export_records(index or committed_index())
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    path.write_text(lines, encoding="utf-8", newline="\n")
    return len(records)
