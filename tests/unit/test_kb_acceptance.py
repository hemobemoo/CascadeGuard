"""PR 3 acceptance (human, 2026-10-30): each query in policies/kb/acceptance.json ranks its
expected page within its limit, against the committed index, with the query vectors stored at
build time (query_vectors.json). No API, no key."""

from typing import Any

import pytest

from cascadeguard.knowledge.kb import (
    KnowledgeBaseError,
    StoredQueries,
    acceptance_queries,
    committed_index,
    search_kb,
)

QUERIES = acceptance_queries()


def test_there_are_the_two_charter_queries_three_more_and_an_arabic_one() -> None:
    texts = [str(q["query"]) for q in QUERIES]
    assert texts[:2] == ["removing AI systems that pose risks", "human oversight of AI decisions"]
    assert len(QUERIES) == 6 and any(not t.isascii() for t in texts)


@pytest.mark.parametrize("spec", QUERIES, ids=[str(q["query"])[:40] for q in QUERIES])
def test_the_expected_page_ranks_within_its_limit(spec: dict[str, Any]) -> None:
    stored = StoredQueries(committed_index().digest)
    hits = search_kb(str(spec["query"]), k=int(spec["within"]), embedder=stored)
    found = [(h.chunk.source_file, h.chunk.page) for h in hits]
    if "expect_page" in spec:
        assert (spec["expect_source"], spec["expect_page"]) in found, found
    else:
        assert any(source in spec["expect_any_source"] for source, _ in found), found


def test_stored_vectors_belong_to_the_committed_index() -> None:
    stored = StoredQueries(committed_index().digest)
    assert set(stored.vectors) == {str(q["query"]) for q in QUERIES}
    with pytest.raises(KnowledgeBaseError, match="another index"):
        StoredQueries("000000000000")
    with pytest.raises(KnowledgeBaseError, match="no stored vector"):
        stored.query("a query nobody embedded")
