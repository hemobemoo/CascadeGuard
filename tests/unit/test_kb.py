"""knowledge/kb.py: the vector index covers exactly the keyword search's pages, under the same
page rules; its digest ignores the vectors; search is deterministic; the export loads into a
ChromaDB kb_main collection the way the reference code loads it (optional `chroma` extra). No
network and no key: a fake embedder, or a fake client behind OpenRouterEmbedder, stands in for
the API."""

import hashlib
import json
import shutil
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cascadeguard.agents.cache import DecisionCache
from cascadeguard.agents.llm import LLMAgent, render_view
from cascadeguard.cli import format_hits, load_world, main
from cascadeguard.domain.policies import TRANSCRIBED_SOURCES, ClauseStatus
from cascadeguard.knowledge import kb
from cascadeguard.knowledge.kb import (
    CHUNK_WORDS,
    DIMENSIONS,
    KB_DIR,
    MAX_CHARS,
    OVERLAP_WORDS,
    Chunk,
    Index,
    KnowledgeBaseError,
    OpenRouterEmbedder,
    Vectors,
    build_chunks,
    chunk_page,
    digest_of,
    export_kb_main,
    export_records,
    load_index,
    search_kb,
    write_index,
)
from cascadeguard.knowledge.loader import (
    EXTRACTED_DIR,
    TRANSCRIPTIONS_DIR,
    ClauseLoadError,
    load_clauses,
    quote_span,
)
from cascadeguard.knowledge.retrieval import (
    NOT_SEARCHED,
    TRANSCRIPTION_CONTEXT_LABEL,
    searchable_pages,
)

CHARTER = next(iter(TRANSCRIBED_SOURCES))


class FakeEmbedder:
    """Bag of words hashed into 64 dimensions: deterministic, no download."""

    def _one(self, text: str) -> list[float]:
        v = [0.0] * 64
        for word in text.casefold().split():
            v[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1.0
        return v

    def documents(self, texts: Sequence[str]) -> Vectors:
        return np.array([self._one(t) for t in texts], dtype=np.float32)

    def query(self, text: str) -> Vectors:
        return np.array([self._one(text)], dtype=np.float32)


@pytest.fixture(scope="module")
def real_chunks() -> list[Chunk]:
    return build_chunks()


def words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_chunks_are_word_windows_with_overlap_and_exact_spans() -> None:
    text = "  " + words(300).replace(" w100 ", " w100\t ")
    chunks = chunk_page("x.pdf", 3, text, "label")
    step = CHUNK_WORDS - OVERLAP_WORDS
    assert [c.id for c in chunks] == ["x.pdf#p3#c0", "x.pdf#p3#c1", "x.pdf#p3#c2"]
    assert [c.text.split()[0] for c in chunks] == ["w0", f"w{step}", f"w{2 * step}"]
    assert [len(c.text.split()) for c in chunks] == [CHUNK_WORDS, CHUNK_WORDS, 300 - 2 * step]
    for c in chunks:
        assert " ".join(text[c.start : c.end].split()) == c.text


def test_a_short_tail_joins_the_previous_chunk() -> None:
    step = CHUNK_WORDS - OVERLAP_WORDS
    assert len(chunk_page("x.pdf", 1, words(CHUNK_WORDS + 20), "l")) == 1
    assert len(chunk_page("x.pdf", 1, words(CHUNK_WORDS + 21), "l")) == 2
    assert chunk_page("x.pdf", 1, words(step), "l")[0].text == words(step)
    assert chunk_page("x.pdf", 1, " \n ", "l") == []


def test_no_chunk_exceeds_the_character_cap() -> None:
    text = " ".join("x" * 40 for _ in range(100))
    chunks = chunk_page("x.pdf", 1, text, "l")
    assert len(chunks) > 1 and all(len(c.text) <= MAX_CHARS for c in chunks)
    assert sum(len(c.text.split()) for c in chunks) == 100


def test_numbered_headings_and_blank_lines_start_their_own_chunk() -> None:
    """Human decision 2026-10-30: each numbered principle or article stands alone."""
    body = " ".join(f"b{i}" for i in range(25))
    text = (
        f"Intro words {body}\n1. First: {body}\n2. Second: {body}\n(a) item {body}\n"
        f"Article 9 heading {body}\n\nAfter a blank line {body}"
    )
    chunks = chunk_page("x.pdf", 1, text, "l")
    assert [c.text.split()[0] for c in chunks] == ["Intro", "1.", "2.", "(a)", "Article", "After"]
    for c in chunks:
        assert " ".join(text[c.start : c.end].split()) == c.text


def test_a_short_segment_joins_the_next_and_a_short_last_one_the_previous() -> None:
    body = " ".join(f"b{i}" for i in range(25))
    text = f"Heading:\n1. Short one.\n2. Long: {body}\n3. Tail."
    chunks = chunk_page("x.pdf", 1, text, "l")
    assert len(chunks) == 1 and chunks[0].text.startswith("Heading: 1. Short one. 2. Long:")
    assert chunks[0].text.endswith("3. Tail.")


def test_each_charter_principle_is_its_own_chunk(real_chunks: list[Chunk]) -> None:
    pages = [c for c in real_chunks if c.source_file == CHARTER and c.page in (3, 4)]
    charter = {c.text.split(":")[0]: c for c in pages}
    assert "2. Safety" in charter and "6. Human Oversight" in charter
    assert [r.id for r in charter["2. Safety"].clauses] == ["uae.ai-charter.safety"]
    assert [r.id for r in charter["6. Human Oversight"].clauses] == [
        "uae.ai-charter.human-oversight"
    ]
    assert "3. Fairness" not in charter["2. Safety"].text


def test_the_index_covers_exactly_the_searchable_pages(real_chunks: list[Chunk]) -> None:
    pages = {(p.source_file, p.page): p.label for p in searchable_pages() if p.text.split()}
    chunks = real_chunks
    assert {(c.source_file, c.page) for c in chunks} == set(pages)
    assert all(c.label == pages[(c.source_file, c.page)] for c in chunks)
    stems = {Path(name).stem.casefold() for name in NOT_SEARCHED}
    for c in chunks:
        assert "abhivardhan" not in c.source_file.casefold()
        assert "oxford handbook" not in c.source_file.casefold()
        if Path(c.source_file).stem.casefold() in stems:  # only the Charter's transcriptions
            assert c.source_file in TRANSCRIBED_SOURCES
            assert c.label == TRANSCRIPTION_CONTEXT_LABEL


def test_the_charter_text_layer_never_reaches_the_index(real_chunks: list[Chunk]) -> None:
    charter = [c for c in real_chunks if c.source_file == CHARTER]
    assert sorted({c.page for c in charter}) == [1, 2, 3, 4, 5]
    assert not any("greatimportance" in c.text for c in charter)  # a text-layer artefact


def charter_rows() -> list[dict[str, Any]]:
    lines = (TRANSCRIPTIONS_DIR / f"{Path(CHARTER).stem}.jsonl").read_text("utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_a_page_that_fails_its_pin_is_refused_by_the_index(tmp_path: Path) -> None:
    stem = Path(CHARTER).stem
    rows = charter_rows()
    rows[3]["text"] += " edited after approval"
    text = "".join(json.dumps(r) + "\n" for r in rows)
    (tmp_path / f"{stem}.jsonl").write_text(text, encoding="utf-8")
    with pytest.raises(ClauseLoadError, match="does not match its approval"):
        build_chunks(transcriptions_dir=tmp_path)


def test_a_draft_transcription_is_never_indexed(tmp_path: Path) -> None:
    stem = Path(CHARTER).stem
    rows = charter_rows()
    rows[3]["status"] = "draft"
    text = "".join(json.dumps(r) + "\n" for r in rows)
    (tmp_path / f"{stem}.jsonl").write_text(text, encoding="utf-8")
    pages = {c.page for c in build_chunks(transcriptions_dir=tmp_path) if c.source_file == CHARTER}
    assert pages == {1, 2, 3, 5}


def test_reviewed_clauses_map_to_the_chunks_holding_their_quote_and_drafts_never(
    real_chunks: list[Chunk],
) -> None:
    chunks = real_chunks
    mapped = {r.id: r.status_label for c in chunks for r in c.clauses}
    clauses = {c.id: c for c in load_clauses()}
    reviewed = [c for c in clauses.values() if c.status is ClauseStatus.REVIEWED]
    for clause in reviewed:
        span = quote_span(clause)
        on_page = [
            c for c in chunks if (c.source_file, c.page) == (clause.source_file, clause.page)
        ]
        if span is None or not on_page:
            assert clause.id not in mapped
            continue
        holders = [c for c in on_page if any(r.id == clause.id for r in c.clauses)]
        assert holders, clause.id
        assert all(c.start < span[1] and span[0] < c.end for c in holders)
        assert mapped[clause.id] == clause.status_label  # the label, never a stronger claim
    assert all(clauses[cid].status is ClauseStatus.REVIEWED for cid in mapped)
    assert "uae.ai-charter.human-oversight" in mapped  # rests on reviewed transcription p.4


def test_the_digest_ignores_the_vectors_and_follows_everything_else(
    tmp_path: Path, real_chunks: list[Chunk], monkeypatch: pytest.MonkeyPatch
) -> None:
    """API vectors can differ slightly between calls: that must not change the digest, so not
    the `+kb:` prompt version or the LLM cache keys either. The build date is not in it."""
    chunks = real_chunks
    a = np.random.default_rng(0).random((len(chunks), DIMENSIONS), dtype=np.float32)
    b = a + np.float32(1e-4)
    first = write_index(chunks, a, "2026-10-30", tmp_path / "a")
    assert write_index(chunks, b, "2026-11-02", tmp_path / "b") == first
    loaded_a, loaded_b = load_index(tmp_path / "a"), load_index(tmp_path / "b")
    assert loaded_a.digest == loaded_b.digest == first
    assert not np.array_equal(loaded_a.vectors, loaded_b.vectors)
    assert digest_of([*chunks[:-1], replace(chunks[-1], text="x")]) != first
    for name, value in [
        ("MODEL_SLUG", "other/model"),
        ("DIMENSIONS", 512),
        ("DOCUMENT_PREFIX", "document: "),
        ("CHUNK_WORDS", 300),
        ("RRF_K", 1),  # test-breaker round 2: ranking settings reach the prompt, so the key
        ("MAX_PER_SOURCE", 1),
        ("PROMPT_K", 5),
        ("RANKING_VERSION", "other"),
    ]:
        with monkeypatch.context() as m:
            m.setattr(kb, name, value)
            assert digest_of(chunks) != first, name


def test_a_stale_or_tampered_index_is_refused(tmp_path: Path, real_chunks: list[Chunk]) -> None:
    chunks = real_chunks
    vectors = np.ones((len(chunks), DIMENSIONS), dtype=np.float32)
    write_index(chunks[:-1], vectors[:-1], "2026-10-30", tmp_path / "stale")
    with pytest.raises(KnowledgeBaseError, match="corpus changed"):
        load_index(tmp_path / "stale")
    write_index(chunks, vectors, "2026-10-30", tmp_path / "tampered")
    path = tmp_path / "tampered" / "chunks.jsonl"
    path.write_text(path.read_text("utf-8").replace("Law", "Lav", 1), encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="manifest digest"):
        load_index(tmp_path / "tampered")
    write_index(chunks, vectors, "2026-10-30", tmp_path / "rows")
    np.save(tmp_path / "rows" / "vectors.npy", vectors[:-1])
    with pytest.raises(KnowledgeBaseError, match="does not match the manifest"):
        load_index(tmp_path / "rows")
    # test-breaker PR 3: reordered rows of the right shape were accepted with the same digest.
    write_index(
        chunks,
        np.random.default_rng(1).random(vectors.shape, dtype=np.float32),
        "d",
        tmp_path / "order",
    )
    stored = np.load(tmp_path / "order" / "vectors.npy")
    np.save(tmp_path / "order" / "vectors.npy", stored[::-1].copy())
    with pytest.raises(KnowledgeBaseError, match="does not match the manifest"):
        load_index(tmp_path / "order")
    with pytest.raises(KnowledgeBaseError, match="1024-dimension"):
        write_index(chunks, vectors[:, :8], "2026-10-30", tmp_path / "dims")


def fake_index() -> Index:
    chunks = [
        Chunk(f"f.pdf#p{p}#c0", "f.pdf", p, 0, len(t), "context only; not citable", t)
        for p, t in enumerate(["incident report duty", "report incident duty", "privacy"], 1)
    ]
    vectors = FakeEmbedder().documents([c.text for c in chunks])
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return Index(tuple(chunks), vectors / norms, {"digest": "fake"})


def test_search_is_deterministic_and_breaks_ties_by_chunk_id() -> None:
    index, embedder = fake_index(), FakeEmbedder()
    hits = search_kb("incident report", k=3, index=index, embedder=embedder)
    assert hits == search_kb("incident report", k=3, index=index, embedder=embedder)
    # p1 and p2 hold the same words: tied in both rankings, so they share rank 1 and the same
    # fused score (human decision 2026-10-30, variant B); the id orders them in the output only.
    # p3 is the same document's third chunk, beyond MAX_PER_SOURCE.
    assert [h.chunk.page for h in hits] == [1, 2]
    assert [(h.vector_rank, h.keyword_rank) for h in hits] == [(1, 1), (1, 1)]
    assert hits[0].score == hits[1].score
    assert search_kb(" ", index=index, embedder=embedder) == ()
    assert search_kb("x", k=0, index=index, embedder=embedder) == ()


def ranked_index(texts: dict[str, str]) -> Index:
    chunks = [
        Chunk(f"{src}#p1#c{n}", src, 1, 0, len(t), "context only; not citable", t)
        for n, (src, t) in enumerate(texts.items())
    ]
    vectors = FakeEmbedder().documents([c.text for c in chunks])
    return Index(tuple(chunks), vectors / np.linalg.norm(vectors, axis=1, keepdims=True), {})


def test_hybrid_ranking_fuses_vector_and_keyword_ranks() -> None:
    """Reciprocal rank fusion (k=60): a chunk ranked well by both lists beats one ranked first by
    one list only; ranks are reported; every tie falls to the chunk id."""
    index = ranked_index(
        {
            "a.pdf": "alpha beta gamma",  # same words as the query: vector #1, keyword #1
            "b.pdf": "alpha alpha delta",  # two query-word hits: keyword #2
            "c.pdf": "unrelated words entirely",  # no query word: keyword-unranked
        }
    )
    hits = search_kb("alpha beta gamma", k=3, index=index, embedder=FakeEmbedder())
    top = hits[0]
    assert top.chunk.source_file == "a.pdf"
    assert (top.vector_rank, top.keyword_rank) == (1, 1)
    assert top.score == pytest.approx(2 / (kb.RRF_K + 1))
    unranked = next(h for h in hits if h.chunk.source_file == "c.pdf")
    assert unranked.keyword_rank is None
    assert unranked.score == pytest.approx(1 / (kb.RRF_K + unranked.vector_rank))


def test_at_most_two_chunks_per_source_reach_the_top_k() -> None:
    index = ranked_index({f"big.pdf{n}": "alpha beta" for n in range(5)} | {"small.pdf": "alpha"})
    chunks = tuple(replace(c, source_file="big.pdf") if "big" in c.id else c for c in index.chunks)
    index = Index(chunks, index.vectors, {})
    hits = search_kb("alpha beta", k=5, index=index, embedder=FakeEmbedder())
    assert [h.chunk.source_file for h in hits] == ["big.pdf", "big.pdf", "small.pdf"]


def test_kb_query_prints_file_page_label_and_clause_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    index = fake_index()
    labelled = kb.ClauseRef("some.clause", "reviewed · not binding")
    first = replace(index.chunks[0], clauses=(labelled,))
    index = Index((first, *index.chunks[1:]), index.vectors, index.manifest)

    def fake_search(text: str, k: int = 5) -> tuple[kb.Hit, ...]:
        return search_kb(text, k, index=index, embedder=FakeEmbedder())

    monkeypatch.setattr("cascadeguard.cli.search_kb", fake_search)
    assert main(["kb", "query", "incident report", "-k", "2"]) == 0
    out = capsys.readouterr().out
    assert "f.pdf  p.1" in out and "f.pdf  p.2" in out and "p.3" not in out
    assert "label: context only; not citable" in out
    assert "clause some.clause: reviewed · not binding" in out
    assert format_hits(()).startswith("Knowledge base: 0 chunks (context only; not citable)")


def load_into_chroma(records: Sequence[dict[str, Any]], client: Any) -> Any:
    """The reference code's load (its kb.py `_col` and `add_documents`): get_or_create_collection
    with cosine distance, then add with pre-computed embeddings, in batches of 5,000."""
    collection = client.get_or_create_collection(name="kb_main", metadata={"hnsw:space": "cosine"})
    for i in range(0, len(records), 5000):
        batch = records[i : i + 5000]
        collection.add(
            ids=[r["id"] for r in batch],
            documents=[r["document"] for r in batch],
            embeddings=[r["embedding"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
        )
    return collection


def test_the_export_loads_into_a_kb_main_collection_like_the_reference(tmp_path: Path) -> None:
    """export_kb_main.jsonl, read back and loaded with the reference code's calls
    (PersistentClient, telemetry off). Not run inside the reference application."""
    chromadb = pytest.importorskip(
        "chromadb", reason="the optional `chroma` extra is not installed (uv sync --extra chroma)"
    )
    index = fake_index()
    path = tmp_path / "export_kb_main.jsonl"
    assert export_kb_main(path, index) == len(index.chunks)
    records = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert records == json.loads(json.dumps(export_records(index)))
    assert all(isinstance(v, str) for r in records for v in r["metadata"].values())
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"), settings=settings)
    collection = load_into_chroma(records, client)
    assert collection.name == "kb_main" and collection.count() == len(index.chunks)
    assert collection.metadata["hnsw:space"] == "cosine"
    got = collection.query(query_embeddings=[records[2]["embedding"]], n_results=1)
    assert got["ids"][0] == [index.chunks[2].id]
    meta = collection.get(ids=[index.chunks[0].id])["metadatas"][0]
    assert meta["source_file"] == "f.pdf" and meta["page"] == "1"


def test_the_committed_index_matches_the_corpus_and_its_manifest() -> None:
    index = load_index()
    m = index.manifest
    assert m["model_slug"] == "nvidia/nemotron-3.5-embed-1b:free"
    assert m["dimensions"] == DIMENSIONS == 1024 and m["build_date"]
    assert index.vectors.shape == (len(index.chunks), DIMENSIONS)
    assert np.allclose(np.linalg.norm(index.vectors, axis=1), 1, atol=1e-5)
    assert (KB_DIR / "chunks.jsonl").exists()


def test_kb_context_enters_only_the_llm_prompt_and_its_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --kb-context the prompt and its version are what they were before PR 3; with it,
    the chunks go in labelled, with the clause status only, and `+kb:<digest>` keys the cache."""
    plain = LLMAgent("r", "m", None, DecisionCache(tmp_path), ("r",))
    with_kb = LLMAgent("r", "m", None, DecisionCache(tmp_path), ("r",), kb_context=True)
    assert plain.prompt_version == "phase5-v4+json_schema"
    assert with_kb.prompt_version == f"phase5-v4+json_schema+kb:{load_index().cache_key}"

    world = load_world("uae_health_access")
    roles = tuple(r.id for r in world.roles.roles)
    views = world.baseline().views
    assert all("knowledge_base_context" not in json.loads(render_view(v, roles)) for v in views)

    index = fake_index()
    labelled = kb.ClauseRef("some.clause", "reviewed · not binding")
    first = replace(index.chunks[0], clauses=(labelled,))
    index = Index((first, *index.chunks[1:]), index.vectors, index.manifest)
    queries: list[str] = []

    def fake_search(text: str, k: int = 5) -> tuple[kb.Hit, ...]:
        queries.append(text)
        return search_kb("incident report", k, index=index, embedder=FakeEmbedder())

    monkeypatch.setattr("cascadeguard.agents.llm.search_kb", fake_search)
    data = json.loads(render_view(views[0], roles, kb=True))["knowledge_base_context"]
    assert data["label"] == "context only; not citable" and "Never cite it" in data["note"]
    assert [c["page"] for c in data["chunks"]] == [1, 2]
    # Human decision 2026-10-30: a role sees only its own citable clauses named on a chunk.
    assert data["chunks"][0]["reviewed_clauses_on_this_text"] == []
    own = next(c for c in views[0].role_clauses if c.citable)
    mine = replace(index.chunks[0], clauses=(kb.ClauseRef(own.id, own.status_label), labelled))
    index = Index((mine, *index.chunks[1:]), index.vectors, index.manifest)
    data = json.loads(render_view(views[0], roles, kb=True))["knowledge_base_context"]
    assert data["chunks"][0]["reviewed_clauses_on_this_text"] == [
        {"id": own.id, "status": own.status_label}
    ]
    assert set(queries) == {" ".join((views[0].event_title, *views[0].decision_points))}


def test_the_index_corpus_equals_the_search_corpus_on_disk_copies(
    tmp_path: Path, real_chunks: list[Chunk]
) -> None:
    """A changed extracted page changes the chunks: the index cannot silently drift."""
    copy = tmp_path / "extracted"
    shutil.copytree(EXTRACTED_DIR, copy)
    base = real_chunks
    target = next(p for p in sorted(copy.glob("*.jsonl")) if p.name.startswith("Dubai"))
    rows = [json.loads(line) for line in target.read_text("utf-8").splitlines() if line]
    rows[0]["text"] += " zzaddedword"
    target.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    changed = build_chunks(copy)
    assert [c.text for c in changed] != [c.text for c in base]
    assert any("zzaddedword" in c.text for c in changed)


waits: list[float] = []  # what the embedder would have slept, in order


class FakeEmbeddings:
    """Stands in for `client.embeddings`: replies in reverse order with 2,048-dimension vectors
    whose first value is the text length, after failing `fail` times."""

    def __init__(self, fail: int = 0) -> None:
        self.fail = fail
        self.inputs: list[list[str]] = []

    def create(self, model: str, input: list[str]) -> Any:
        self.inputs.append(input)
        if self.fail:
            self.fail -= 1
            raise ConnectionError("network down")
        rows = [
            type("D", (), {"index": i, "embedding": [float(len(t)), *range(1, 2048)]})()
            for i, t in enumerate(input)
        ]
        return type("R", (), {"data": rows[::-1]})()


def api_embedder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeEmbeddings
) -> OpenRouterEmbedder:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")  # never called
    embedder = OpenRouterEmbedder(env_file=tmp_path / "none.env")
    setattr(embedder, "_client", type("C", (), {"embeddings": fake})())  # noqa: B010
    embedder.sleep = waits.append
    return embedder


def test_the_api_embedder_batches_prefixes_truncates_and_renormalises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeEmbeddings()
    embedder = api_embedder(monkeypatch, tmp_path, fake)
    texts = [f"text {i} " * (i + 1) for i in range(70)]
    vectors = embedder.documents(texts)
    assert [len(b) for b in fake.inputs] == [32, 32, 6]
    assert all(t.startswith("passage: ") for b in fake.inputs for t in b)
    assert vectors.shape == (70, DIMENSIONS)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)
    # Row order follows the request, whatever order the reply lists them in.
    expected = np.array([len("passage: " + texts[5]), *range(1, DIMENSIONS)], dtype=np.float64)
    assert np.allclose(vectors[5], expected / np.linalg.norm(expected), atol=1e-6)
    embedder.query("who decides")
    assert fake.inputs[-1] == ["query: who decides"]


def test_the_api_embedder_retries_three_times_then_stops_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    waits.clear()
    embedder = api_embedder(monkeypatch, tmp_path, FakeEmbeddings(fail=3))
    assert embedder.query("x").shape == (1, DIMENSIONS) and embedder.requests == 4
    backoffs = [w for w in waits if w >= 10]
    assert backoffs == [10.0, 20.0, 40.0]  # no Retry-After header: doubling backoff
    assert all(w <= kb.PACE_SECONDS + 1e-6 for w in waits if w < 10), waits  # pacing
    embedder = api_embedder(monkeypatch, tmp_path, FakeEmbeddings(fail=4))
    with pytest.raises(KnowledgeBaseError, match="failed 4 times") as err:
        embedder.query("x")
    assert "sk-test" not in str(err.value) and embedder.requests == 4


def test_without_a_key_kb_query_and_kb_context_fail_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(kb, "PROJECT_ROOT", tmp_path)  # no .env here
    kb._embedder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    try:
        assert main(["kb", "query", "who reverses the lockout"]) == 2
        out = capsys.readouterr().out
        assert "OPENROUTER_API_KEY, OPENROUTER_BASE_URL" in out and "Traceback" not in out
    finally:
        kb._embedder.cache_clear()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(KnowledgeBaseError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder(env_file=tmp_path / "none.env")


def test_the_scripted_demo_and_keyword_path_never_touch_the_embedding_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cascadeguard.knowledge.retrieval import search_extracted

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("the embedding API was used")

    monkeypatch.setattr(kb.OpenRouterEmbedder, "__init__", refuse)
    monkeypatch.setattr(kb, "search_kb", refuse)
    monkeypatch.setattr("cascadeguard.cli.search_kb", refuse)
    monkeypatch.setattr("cascadeguard.agents.llm.search_kb", refuse)
    assert main(["run", "uae_health_access"]) == 0
    assert search_extracted("incident report", limit=2)


@pytest.mark.parametrize(
    "corrupt",
    ["manifest not json", "manifest without digest", "chunk without label", "vectors not npy"],
)
def test_a_malformed_index_is_a_clear_error_not_a_traceback(
    tmp_path: Path,
    corrupt: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """test-breaker PR 3: malformed files raised KeyError or JSONDecodeError through the CLI."""
    shutil.copytree(KB_DIR, tmp_path / "kb")
    kb_dir = tmp_path / "kb"
    manifest = kb_dir / "manifest.json"
    if corrupt == "manifest not json":
        manifest.write_text("{not json", encoding="utf-8")
    elif corrupt == "manifest without digest":
        data = json.loads(manifest.read_text("utf-8"))
        del data["digest"]
        manifest.write_text(json.dumps(data), encoding="utf-8")
    elif corrupt == "chunk without label":
        path = kb_dir / "chunks.jsonl"
        lines = path.read_text("utf-8").splitlines()
        first = json.loads(lines[0])
        del first["label"]
        path.write_text("\n".join([json.dumps(first), *lines[1:]]), encoding="utf-8")
    else:
        (kb_dir / "vectors.npy").write_bytes(b"not an npy file")
    with pytest.raises(KnowledgeBaseError, match="malformed index"):
        load_index(kb_dir)

    def stale() -> Index:
        return load_index(kb_dir)

    monkeypatch.setattr(kb, "committed_index", stale)
    assert main(["kb", "export", str(tmp_path / "out.jsonl")]) == 2
    out = capsys.readouterr().out
    assert "malformed index" in out and "Traceback" not in out


def test_kb_export_writes_every_committed_chunk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "export_kb_main.jsonl"
    assert main(["kb", "export", str(path)]) == 0
    records = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert len(records) == len(load_index().chunks) and len(records[0]["embedding"]) == DIMENSIONS
    assert "ChromaDB kb_main format" in capsys.readouterr().out


def test_llm_run_with_kb_context_stops_cleanly_on_a_bad_index_or_lost_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """test-breaker PR 3: the CLI pre-check and the mid-run handler for --kb-context had no test."""
    monkeypatch.setenv("CASCADEGUARD_MODEL", "test/model")

    def bad_index() -> str:
        raise KnowledgeBaseError("the corpus changed since the index was built: rebuild it")

    monkeypatch.setattr("cascadeguard.cli.index_digest", bad_index)
    args = ["run", "uae_health_access", "--agents", "llm", "--offline", "--kb-context"]
    assert main([*args, "--cache", str(tmp_path / "cache")]) == 2
    out = capsys.readouterr().out
    assert "rebuild it" in out and "Traceback" not in out
    monkeypatch.undo()

    # Mid-run: the query embedding fails after the run has started.
    from cascadeguard.cli import World

    def lost(self: World) -> None:
        raise KnowledgeBaseError("OpenRouter embeddings failed 4 times: ConnectionError")

    monkeypatch.setattr(World, "baseline", lost)
    assert main(["run", "uae_health_access"]) == 2
    out = capsys.readouterr().out
    assert "failed 4 times" in out and "Traceback" not in out


def test_ties_go_to_the_chunk_id_not_the_storage_order() -> None:
    """test-breaker round 2: with the index stored in id order, a stable sort hid a missing
    tie-break. Stored in reverse, the result must still follow the ids."""
    index = fake_index()
    reverse = Index(index.chunks[::-1], index.vectors[::-1], index.manifest)
    hits = search_kb("incident report", k=2, index=reverse, embedder=FakeEmbedder())
    assert [h.chunk.page for h in hits] == [1, 2]


def test_the_loaded_vectors_cannot_be_changed() -> None:
    with pytest.raises(ValueError):
        load_index().vectors[0, 0] = 0.0


def test_the_embedder_refuses_a_host_other_than_openrouter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AGENTS.md (amended 2026-10-30): the key and corpus text go only to openrouter.ai."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-real-key")
    for url in (
        "http://example.invalid/v1",
        "https://openrouter.ai.evil.test/api/v1",
        "http://openrouter.ai/api/v1",
        "https://user@[SECRETTOKEN123]/api/v1",
    ):
        monkeypatch.setenv("OPENROUTER_BASE_URL", url)
        with pytest.raises(KnowledgeBaseError, match=r"must point at openrouter\.ai") as err:
            OpenRouterEmbedder(env_file=tmp_path / "none.env")
        assert "sk-test" not in str(err.value) and url not in str(err.value)


def test_tied_scores_share_the_best_rank() -> None:
    """Variant B (human decision 2026-10-30): equal scores take the same, best rank; the next
    distinct score takes its position (competition ranking)."""
    assert kb.shared_ranks({7: 0.9, 3: 0.5, 5: 0.9, 1: 0.2, 2: 0.5}) == {
        7: 1,
        5: 1,
        3: 3,
        2: 3,
        1: 5,
    }
    assert kb.shared_ranks({}) == {}


def test_kb_query_survives_a_legacy_console_code_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """test-breaker round 3: chunk text with U+F0B7 crashed `kb query` on a cp1252 stdout."""
    import io
    import sys

    index = fake_index()
    odd = replace(index.chunks[0], text="bullet \uf0b7 arrow \u25bc incident report")
    index = Index((odd, *index.chunks[1:]), index.vectors, index.manifest)

    def fake_search(text: str, k: int = 5) -> tuple[kb.Hit, ...]:
        return search_kb(text, k, index=index, embedder=FakeEmbedder())

    monkeypatch.setattr("cascadeguard.cli.search_kb", fake_search)
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    assert main(["kb", "query", "incident report"]) == 0
    sys.stdout.flush()
    assert b"incident report" in raw.getvalue()


def test_a_deeply_nested_or_empty_file_is_a_clear_error(tmp_path: Path) -> None:
    shutil.copytree(KB_DIR, tmp_path / "kb")
    (tmp_path / "kb" / "chunks.jsonl").write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="malformed index"):
        load_index(tmp_path / "kb")
    (tmp_path / "kb" / "query_vectors.json").write_text("{}", encoding="utf-8")
    with pytest.raises(KnowledgeBaseError, match="malformed query_vectors"):
        kb.StoredQueries("x", tmp_path / "kb")


@pytest.mark.parametrize("bad", ["nan", "zero"])
def test_a_nan_or_zero_query_vector_is_refused(bad: str) -> None:
    """test-breaker round 3: NaN ranked arbitrarily; all zeros tied every chunk."""

    class Bad:
        def documents(self, texts: Sequence[str]) -> Vectors:
            raise AssertionError

        def query(self, text: str) -> Vectors:
            vector = np.zeros((1, 64), dtype=np.float32)
            if bad == "nan":
                vector[0, 0] = np.nan
            return vector

    with pytest.raises(KnowledgeBaseError, match="not finite or is all zeros"):
        search_kb("incident", index=fake_index(), embedder=Bad())


def test_swapping_two_vector_rows_changes_the_kb_cache_key(tmp_path: Path) -> None:
    """Human decision 2026-10-30: the --kb-context cache key includes the vectors' SHA-256, so
    changed vectors refresh the cache; the digest alone stays the same."""
    shutil.copytree(KB_DIR, tmp_path / "kb")
    kb_dir = tmp_path / "kb"
    committed = load_index(kb_dir)
    vectors = np.load(kb_dir / "vectors.npy")
    vectors[[0, 1]] = vectors[[1, 0]]
    np.save(kb_dir / "vectors.npy", vectors, allow_pickle=False)
    manifest = json.loads((kb_dir / "manifest.json").read_text("utf-8"))
    manifest["vectors_sha256"] = hashlib.sha256((kb_dir / "vectors.npy").read_bytes()).hexdigest()
    (kb_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    swapped = load_index(kb_dir)
    assert swapped.digest == committed.digest
    assert swapped.cache_key != committed.cache_key
    assert committed.cache_key.startswith(committed.digest + ".")
