"""Task 4: the retrieval evaluation runs with no API on stored query vectors, its report is
current, and the preset vectors embedded in the same request are not wired in."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from cascadeguard.agents.adviser_query import PRESET_VECTORS, load_presets
from cascadeguard.knowledge.kb import BATCH, KB_DIR, MODEL_SLUG, Chunk, Hit, load_index

ROOT = Path(__file__).resolve().parents[2]
TOPICS = {
    "AI governance",
    "health data sharing",
    "telecom duties",
    "incident response",
    "information sharing",
    "human oversight",
    "fallback arrangements",
    "should find nothing",
}


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def queries() -> list[dict[str, Any]]:
    path = ROOT / "tests" / "evaluation" / "kb_queries.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["queries"]


def test_the_report_is_current() -> None:
    text = script("kb_retrieval_eval").render()
    committed = (ROOT / "docs" / "evaluation" / "kb-retrieval.md").read_text(encoding="utf-8")
    assert committed.replace("\r\n", "\n") == text


def test_the_queries_cover_the_brief_and_expect_indexed_pages_only() -> None:
    qs = queries()
    assert {q["topic"] for q in qs} == TOPICS
    assert sum(q.get("expect") == "nothing" for q in qs) == 3
    indexed = {(c.source_file, c.page) for c in load_index().chunks}
    for q in qs:
        if q.get("expect") == "nothing":
            continue
        pages = [(q["expect_source"], q["expect_page"])]
        pages += [(a["source"], a["page"]) for a in q.get("also_relevant", [])]
        for source, page in pages:
            assert (source, page) in indexed, (q["id"], source, page)
            assert "NIST" not in str(source), q["id"]


def stored(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_stored_vectors_hold_the_queries_and_presets_with_the_index_model() -> None:
    """The stored data only: which texts, which model and index, and that they fit one batch.
    The number of requests actually sent is not recorded here (the script printed it)."""
    digest = load_index().digest
    evaluation = stored(ROOT / "tests" / "evaluation" / "kb_query_vectors.json")
    pending = stored(KB_DIR / "adviser_query_vectors.pending.json")
    presets = [t for _, t in load_presets(ROOT / "scenarios" / "uae_health_access")]
    for data in (evaluation, pending):
        assert (data["index_digest"], data["model_slug"]) == (digest, MODEL_SLUG)
    assert list(evaluation["vectors"]) == [q["query"] for q in queries()]
    assert list(pending["vectors"]) == presets
    assert len(queries()) + len(presets) <= BATCH  # one batch: one request


def test_the_preset_vectors_are_not_wired_in() -> None:
    """Human, 2026-11-06: the preset vectors are not wired in: no source file names the
    pending file and the file the adviser reads does not exist. (Preset cache keys and recorded
    answers are pinned by their own tests.)"""
    assert PRESET_VECTORS == "adviser_query_vectors.json"
    assert not (KB_DIR / PRESET_VECTORS).exists()
    for path in (ROOT / "src").rglob("*.py"):
        assert ".pending" not in path.read_text(encoding="utf-8"), path


def chunk(source: str, page: int, n: int, also_in: tuple[str, ...] = (), dup: str | None = None):
    return Chunk(f"{source}#p{page}#c{n}", source, page, 0, 1, "label", "text", (), dup, also_in)


def test_the_metric_formulas_on_a_hand_built_ranking() -> None:
    """Known answers: a relevant page reached through an exact copy, two chunks of one relevant
    page, a non-relevant chunk first; the copy itself is not ranked and adds no ceiling."""
    ev = script("kb_retrieval_eval")
    a1, a1b, a2 = chunk("A.pdf", 1, 0), chunk("A.pdf", 1, 1), chunk("A.pdf", 2, 0)
    b3 = chunk("B.pdf", 3, 0, also_in=("C.pdf#p9#c0",))
    c9 = chunk("C.pdf", 9, 0, dup=b3.id)
    d1 = chunk("D.pdf", 1, 0)
    also = [{"source": "C.pdf", "page": 9}]
    q = {"expect_source": "A.pdf", "expect_page": 1, "also_relevant": also}
    hits = tuple(Hit(1.0 - i / 10, c) for i, c in enumerate((a2, b3, a1, d1)))
    scored = ev.score(q, hits, (a1, a1b, a2, b3, c9, d1))
    assert scored.flags == (False, True, True, False)
    assert scored.first == 2 and scored.rr == 0.5
    assert scored.p3 == pytest.approx(2 / 3)
    assert scored.r5 == 1.0  # A p.1 and C p.9 (through B's copy) both found
    assert scored.ceiling == 1.0  # A: 2 chunks (cap 2), B: 1 through its copy
    lone = ev.score({"expect_source": "D.pdf", "expect_page": 1}, (), (a1, d1))
    assert (lone.first, lone.rr, lone.p3, lone.r5) == (None, 0.0, 0.0, 0.0)
    assert lone.ceiling == pytest.approx(1 / 3)


def test_every_miss_has_exactly_one_cause() -> None:
    """Test-breaker round 2: a relevant hit returned at rank 6-10 is its own cause."""
    cause = script("kb_retrieval_eval").miss_cause
    assert [cause(f, 1) for f in (1, 5)] == [None, None]
    assert cause(7, 3) == "late"  # returned at rank 7: neither capped nor below
    assert cause(None, 3) == "cap"  # in the fused top 10 before the cap, none returned
    assert cause(None, 25) == "below"


def run_embed(monkeypatch: pytest.MonkeyPatch, texts: list[str], presets: list[str], *args: str):
    module = script("embed_eval_queries")

    def no_network() -> None:
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(module, "eval_queries", lambda: texts)

    def fake_presets(_path: Path) -> tuple[tuple[int, str], ...]:
        return tuple((0, t) for t in presets)

    monkeypatch.setattr(module, "load_presets", fake_presets)
    monkeypatch.setattr(module, "OpenRouterEmbedder", no_network)
    monkeypatch.setattr(sys, "argv", ["embed_eval_queries.py", *args])
    return module


def test_the_embed_script_dry_run_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = run_embed(monkeypatch, ["a", "b"], ["c"])
    assert module.main() == 0
    assert "3 texts, 1 request(s)" in capsys.readouterr().out


def test_the_embed_script_refuses_a_repeated_text(monkeypatch: pytest.MonkeyPatch) -> None:
    module = run_embed(monkeypatch, ["a", "b"], ["a"], "--run")
    assert module.main() == 2


def test_the_embed_script_refuses_more_than_one_request(monkeypatch: pytest.MonkeyPatch) -> None:
    module = run_embed(monkeypatch, [str(i) for i in range(BATCH)], ["extra"], "--run")
    assert module.main() == 2


def test_the_readme_states_the_embedding_compatibility() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    note = readme.split("**Embedding compatibility.**", 1)[1].split("\n\n", 1)[0]
    note = " ".join(note.split())
    for words in (
        "`nvidia/nemotron-3.5-embed-1b`",
        "`nomic-embed-text`",
        "same model",
        "`query: `",
        "not been run inside the reference application",
        "not hosted in the ITU AI for Good Lab",
    ):
        assert words in note, words
