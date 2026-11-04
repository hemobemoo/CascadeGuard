"""docs/citation-map.md stays equal to what scripts/citation_map.py builds from committed data,
and every clause an agent cited is in the loaded clause set."""

import importlib.util
import json
from types import ModuleType

import pytest

from cascadeguard.knowledge.loader import PROJECT_ROOT, load_engine_clauses


@pytest.fixture(scope="module")
def cmap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "citation_map", PROJECT_ROOT / "scripts" / "citation_map.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_map_is_current(cmap: ModuleType) -> None:
    committed = cmap.OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert cmap.build() == committed, "run: uv run python scripts/citation_map.py"


def test_every_cited_clause_is_in_the_loaded_clause_set(cmap: ModuleType) -> None:
    loaded = load_engine_clauses()
    citations = cmap.all_citations()
    assert {c.run for c in citations} == set(cmap.RUNS)
    for c in citations:
        assert c.clause_id in loaded, c
        assert f"`{c.clause_id}`" in cmap.OUTPUT.read_text(encoding="utf-8")


def test_an_unknown_clause_stops_the_build(cmap: ModuleType) -> None:
    loaded = load_engine_clauses()
    del loaded["dha.pp11.4-18-2"]
    with pytest.raises(cmap.CitationMapError, match=r"dha\.pp11\.4-18-2"):
        cmap.build(loaded)


def test_rejections_match_the_exports(cmap: ModuleType) -> None:
    """Each rejected decision's offending clause carries its reason, in each run that rejected
    it, and nothing else is marked rejected except the rest of that same decision."""
    exports = {
        cmap.SCRIPTED: json.loads(cmap.SCRIPTED_TRACE.read_text(encoding="utf-8")),
        cmap.LIVE_GOVERNED: json.loads(cmap.LIVE_BASELINE.read_text(encoding="utf-8")),
        cmap.LIVE_UNGOVERNED: json.loads(cmap.LIVE_GOVERNANCE_OFF.read_text(encoding="utf-8"))[
            "ungoverned_run"
        ],
    }
    expected: set[tuple[str, str, int, str]] = set()
    for run, export in exports.items():
        for r in export["rejected_decisions"]:
            for clause in r["clauses"]:
                expected.add((run, r["role"], r["minute"], clause["id"]))
    assert expected, "the live runs record one rejected decision"
    citations = cmap.all_citations()
    offending = {
        (c.run, c.role, c.minute, c.clause_id)
        for c in citations
        if c.verdict.startswith("rejected: ") and "whole decision" not in c.verdict
    }
    assert offending == expected
    rejected_steps = {(run, role, minute) for run, role, minute, _ in expected}
    for c in citations:
        if (c.run, c.role, c.minute) in rejected_steps:
            assert c.verdict != "accepted", c
        else:
            assert c.verdict == "accepted", c


def test_each_live_run_maps_every_cached_step(cmap: ModuleType) -> None:
    """The ungoverned run reused the governed run's decisions except the health service
    operator's from T+30 on (docs/evaluation/gate4/README.md)."""
    by_run: dict[str, set[tuple[str, int, str]]] = {}
    for c in cmap.live_citations():
        by_run.setdefault(c.run, set()).add((c.role, c.minute, c.clause_id))
    differing = by_run[cmap.LIVE_GOVERNED] ^ by_run[cmap.LIVE_UNGOVERNED]
    assert differing
    assert all(role == "health_service_operator" and m >= 30 for role, m, _ in differing)
