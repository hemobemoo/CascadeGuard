"""PR 5: the generated evaluation documents stay equal to what the engine produces, quote their
clauses verbatim, keep every qualification, and follow the human's wording rules (gate 7)."""

import json
import re
from pathlib import Path

import pytest

from cascadeguard.engine.constraints import GAP_CLAIM, OVERSTATED
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.storage import reports
from cascadeguard.storage.reports import (
    CONCLUSION_DRAFT,
    GAP_ANALYSIS,
    LIVE_LLM,
    SCRIPTED,
    TRACES_DIR,
    WITHOUT_AUTHORITY,
    ScriptedRuns,
    build,
    load_gap_examples,
    reviewed_example_clauses,
)


@pytest.fixture(scope="module")
def built() -> dict[Path, str]:
    return build()


@pytest.fixture(scope="module")
def runs() -> ScriptedRuns:
    return reports.scripted_runs()


def committed(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")  # checkouts may use CRLF


def test_every_generated_file_is_committed_unchanged(built: dict[Path, str]) -> None:
    assert len(built) == 8
    for path, text in built.items():
        assert committed(path) == text, f"{path.name} is stale: run scripts/build_reports.py"
    generated = {p.name for p in built if p.parent == TRACES_DIR}
    assert {p.name for p in TRACES_DIR.iterdir()} == {*generated, "how-to-read.md"}


def test_traces_are_the_three_scripted_runs(runs: ScriptedRuns) -> None:
    base = json.loads(committed(TRACES_DIR / "uae_health_access-baseline.json"))
    off = json.loads(committed(TRACES_DIR / "uae_health_access-governance-off.json"))
    rep = json.loads(committed(TRACES_DIR / "uae_health_access-replay-rank1.json"))
    assert base["agents"] == off["agents"] == rep["agents"] == runs.baseline.agents
    assert runs.baseline.scripted and runs.rank1.replay.scripted
    assert rep["repair"] == runs.search.ranked[0].proposal.repair_id
    assert off["ungoverned_run"]["governance"] == "off" and "governance" not in base


def test_gap_examples_name_reviewed_clauses_and_diagnosed_failures(runs: ScriptedRuns) -> None:
    examples = load_gap_examples()
    corpus = {c.id: c for c in load_clauses()}
    assert reviewed_example_clauses(examples, corpus)
    failures = {f.id for f in runs.baseline.failures}
    assert {e.failure for e in examples.entries} <= failures
    for e in examples.entries:  # the relevance line is not itself a gap claim or overstated
        assert not GAP_CLAIM.search(e.relevance) and not OVERSTATED.search(e.relevance), e
    # A draft mapping has no approved entry and is labelled as a draft in the document.
    if examples.status == "draft":
        assert not any(e.approved for e in examples.entries)
        assert "DRAFT mapping awaiting the human's approval (gate 7)" in committed(GAP_ANALYSIS)


def test_gap_analysis_quotes_verbatim_and_keeps_every_qualification(runs: ScriptedRuns) -> None:
    text = committed(GAP_ANALYSIS)
    corpus = {c.id: c for c in load_clauses()}
    for f in runs.baseline.failures:
        assert f"## `{f.id}`" in text and f"_{f.qualification}_" in text
    quoted = [line.removeprefix("  > ") for line in text.splitlines() if line.startswith("  > ")]
    assert quoted
    texts = [c.text for c in corpus.values()]
    for line in quoted:
        assert any(line in t for t in texts), line
    for cid in re.findall(r"`([a-z0-9.\-]+)` \[", text):
        assert cid in corpus and f"`{cid}` [{corpus[cid].status_label}]" in text


def test_the_conclusion_draft_follows_the_human_rules(runs: ScriptedRuns) -> None:
    text = committed(CONCLUSION_DRAFT)
    assert text.startswith("# DRAFT conclusion wording (gate 7): not published")
    assert "unauthori" not in text.lower()
    assert text.count(WITHOUT_AUTHORITY) == 2
    main, live = text.split("## Supporting evidence", 1)
    # The three scripted runs together, each labelled; governed vs ungoverned never alone.
    for run in ("**Governed** (", "**Ungoverned** (", "**Governed with the rank-1 repair** ("):
        assert f"{run}{SCRIPTED}" in main
    assert LIVE_LLM not in main and live.count(LIVE_LLM) == 2
    # The repair's masked blockers and its authorization label are stated.
    rep = runs.rank1
    assert len(rep.masked) == 2 and all(f"`{m}`" in main for m in rep.masked)
    assert "requires authorization" in main and rep.proposal.requires_authorization
    assert rep.outcome == "resolved" and not rep.unmet_critical_goals
    assert "No live repair replay was run" in live


def test_no_generated_document_publishes_the_draft() -> None:
    for path in (
        Path("README.md"),
        Path("docs/architecture.md"),
        GAP_ANALYSIS,
        *TRACES_DIR.iterdir(),
    ):
        assert "pr5-conclusion-draft" not in path.read_text(encoding="utf-8"), path
