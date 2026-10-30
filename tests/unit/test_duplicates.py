"""Exact duplicates collapse to one primary result, in the keyword search and the vector index
alike (human decision 2026-10-30): a reviewed transcription first, then an original a reviewed
clause quotes, then by id. Copies are listed under "also in", take no top-k slot and do not
count toward the per-document limit. Nothing is removed from any source."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cascadeguard.cli import format_hits, main
from cascadeguard.knowledge.kb import (
    Chunk,
    ClauseRef,
    Index,
    StoredQueries,
    Vectors,
    collapse_duplicates,
    committed_index,
    search_kb,
)
from cascadeguard.knowledge.retrieval import (
    CONTEXT_LABEL,
    TRANSCRIPTION_CONTEXT_LABEL,
    primary_key,
    search_extracted,
    text_key,
)


class FakeEmbedder:
    """Bag of words hashed into 64 dimensions: deterministic, no API."""

    def _one(self, text: str) -> list[float]:
        v = [0.0] * 64
        for word in text.casefold().split():
            v[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1.0
        return v

    def documents(self, texts: Sequence[str]) -> Vectors:
        return np.array([self._one(t) for t in texts], dtype=np.float32)

    def query(self, text: str) -> Vectors:
        return np.array([self._one(text)], dtype=np.float32)


CHARTER = "The UAE Charter for the Development and Use of Artificial Intelligence.pdf"
FOUNDATION = "UAE Policy Foundation.pdf"


def test_the_primary_is_a_transcription_then_a_quoted_original_then_the_id() -> None:
    transcription = primary_key(TRANSCRIPTION_CONTEXT_LABEL, False, "z")
    assert transcription < primary_key(CONTEXT_LABEL, True, "a")
    assert primary_key(CONTEXT_LABEL, True, "z") < primary_key(CONTEXT_LABEL, False, "a")
    assert primary_key(CONTEXT_LABEL, False, "a") < primary_key(CONTEXT_LABEL, False, "b")
    assert text_key("a  b\nc") == text_key("a b c") != text_key("a b d")
    assert text_key(" \n ") == ""


def pair_index() -> Index:
    """A made-up pair: 'b.pdf' copies a passage of 'z.pdf', which a reviewed clause quotes; plus
    two more chunks of 'b.pdf' and one of 'c.pdf'."""
    text = "incident report duty owner"
    clause = (ClauseRef("x.clause", "reviewed"),)
    chunks = [
        Chunk("b.pdf#p1#c0", "b.pdf", 1, 0, 1, CONTEXT_LABEL, text),
        Chunk("b.pdf#p2#c0", "b.pdf", 2, 0, 1, CONTEXT_LABEL, "incident report duty"),
        Chunk("b.pdf#p3#c0", "b.pdf", 3, 0, 1, CONTEXT_LABEL, "incident report"),
        Chunk("c.pdf#p1#c0", "c.pdf", 1, 0, 1, CONTEXT_LABEL, "incident"),
        Chunk("z.pdf#p9#c0", "z.pdf", 9, 0, 1, CONTEXT_LABEL, text, clause),
    ]
    collapsed = collapse_duplicates(chunks)
    vectors = FakeEmbedder().documents([c.text for c in collapsed])
    return Index(tuple(collapsed), vectors / np.linalg.norm(vectors, axis=1, keepdims=True), {})


def test_a_made_up_duplicate_pair_collapses_into_one_result() -> None:
    index = pair_index()
    copy, primary = index.chunks[0], index.chunks[4]
    assert copy.duplicate_of == primary.id and primary.also_in == (copy.id,)
    assert primary.copies == ("b.pdf p.1",)
    hits = search_kb("incident report duty owner", k=5, index=index, embedder=FakeEmbedder())
    ids = [h.chunk.id for h in hits]
    assert "b.pdf#p1#c0" not in ids and ids[0] == "z.pdf#p9#c0"
    # The copy took no slot and did not count toward b.pdf's limit of 2.
    assert [h.chunk.source_file for h in hits].count("b.pdf") == 2
    assert "   also in: b.pdf p.1" in format_hits(hits)


def test_a_transcription_wins_over_an_original_whatever_the_names() -> None:
    text = "the same principle text"
    chunks = [
        Chunk("0 first.pdf#p1#c0", "0 first.pdf", 1, 0, 1, CONTEXT_LABEL, text),
        Chunk("zz.pdf#p4#c1", "zz.pdf", 4, 0, 1, TRANSCRIPTION_CONTEXT_LABEL, text),
    ]
    first, second = collapse_duplicates(chunks)
    assert first.duplicate_of == "zz.pdf#p4#c1" and second.also_in == ("0 first.pdf#p1#c0",)


def test_charter_p4_stays_in_the_top_3_with_the_tie_break_reversed() -> None:
    """test-breaker round 2: Charter p.4 reached the top 3 only because its file name sorts
    before the Policy Foundation's, which holds the same text. Rename the Policy Foundation so
    it sorts first and collapse again: the Charter page is still the primary and still ranks."""
    index = committed_index()

    def renamed(c: Chunk) -> Chunk:
        if c.source_file != FOUNDATION:
            return replace(c, duplicate_of=None, also_in=())
        first = "0" + FOUNDATION  # now sorts before the Charter
        return replace(c, id="0" + c.id, source_file=first, duplicate_of=None, also_in=())

    chunks = collapse_duplicates([renamed(c) for c in index.chunks])
    reversed_index = Index(tuple(chunks), index.vectors, index.manifest)
    p4 = next(c for c in chunks if c.source_file == CHARTER and c.text.startswith("6. Human"))
    assert p4.duplicate_of is None and any(i.startswith("0" + FOUNDATION) for i in p4.also_in)
    stored = StoredQueries(index.digest)
    hits = search_kb("human oversight of AI decisions", k=3, index=reversed_index, embedder=stored)
    assert (CHARTER, 4) in [(h.chunk.source_file, h.chunk.page) for h in hits]
    assert all(not h.chunk.source_file.endswith(FOUNDATION) or h.chunk.page != 2 for h in hits)


def test_the_committed_index_collapses_the_foundation_copies_into_the_charter() -> None:
    chunks = committed_index().chunks
    p4 = next(c for c in chunks if c.source_file == CHARTER and c.text.startswith("6. Human"))
    assert f"{FOUNDATION} p.2" in p4.copies
    copy = next(c for c in chunks if c.id in p4.also_in)
    assert copy.duplicate_of == p4.id and copy.source_file == FOUNDATION  # kept, not removed


def test_the_keyword_search_collapses_identical_pages_the_same_way(tmp_path: Path) -> None:
    rows = {
        "a.jsonl": [{"source_file": "a.pdf", "page": 3, "text": "incident report duty"}],
        "b.jsonl": [{"source_file": "b.pdf", "page": 1, "text": "incident  report\nduty"}],
        "c.jsonl": [{"source_file": "c.pdf", "page": 1, "text": "incident report"}],
    }
    for name, pages in rows.items():
        (tmp_path / name).write_text("\n".join(json.dumps(p) for p in pages), encoding="utf-8")
    empty = tmp_path / "none"
    empty.mkdir()
    query = "incident report duty"
    found = search_extracted(query, extracted_dir=tmp_path, transcriptions_dir=empty)
    assert [(s.source_file, s.page, s.also_in) for s in found] == [
        ("a.pdf", 3, ("b.pdf p.1",)),
        ("c.pdf", 1, ()),
    ]
    one = search_extracted("incident report duty", 1, tmp_path, transcriptions_dir=empty)
    assert [s.source_file for s in one] == ["a.pdf"]  # the copy took no place in the limit


def test_kb_context_with_scripted_agents_stops_with_a_clear_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Human decision 2026-10-30: never silently ignored."""
    assert main(["run", "uae_health_access", "--kb-context"]) == 2
    out = capsys.readouterr().out
    assert "--kb-context gives context to LLM agents only" in out and "Traceback" not in out
    assert main(["repairs", "uae_health_access", "--kb-context"]) == 2
