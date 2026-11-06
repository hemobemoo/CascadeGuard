"""Task 4: the retrieval evaluation runs with no API on stored query vectors, its report is
current, and the preset vectors embedded in the same request are not wired in."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from cascadeguard.agents.adviser_query import PRESET_VECTORS, load_presets
from cascadeguard.knowledge.kb import KB_DIR, MODEL_SLUG, load_index

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


def test_one_request_held_the_queries_and_the_presets_with_the_index_model() -> None:
    digest = load_index().digest
    evaluation = stored(ROOT / "tests" / "evaluation" / "kb_query_vectors.json")
    pending = stored(KB_DIR / "adviser_query_vectors.pending.json")
    presets = [t for _, t in load_presets(ROOT / "scenarios" / "uae_health_access")]
    for data in (evaluation, pending):
        assert (data["index_digest"], data["model_slug"]) == (digest, MODEL_SLUG)
    assert list(evaluation["vectors"]) == [q["query"] for q in queries()]
    assert list(pending["vectors"]) == presets
    assert len(queries()) + len(presets) <= 32  # one batch: one request


def test_the_preset_vectors_are_not_wired_in() -> None:
    """Human, 2026-11-06: the preset cache keys, recorded answers and report stay unchanged."""
    assert PRESET_VECTORS == "adviser_query_vectors.json"
    assert not (KB_DIR / PRESET_VECTORS).exists()
    for path in (ROOT / "src").rglob("*.py"):
        assert ".pending" not in path.read_text(encoding="utf-8"), path
