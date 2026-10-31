"""PR 5: the generated evaluation documents stay equal to what the engine produces, quote their
clauses verbatim, keep every qualification, and follow the human's wording rules (gate 7)."""

import json
import re
from pathlib import Path

import pytest

from cascadeguard.engine.constraints import GAP_CLAIM, OVERSTATED
from cascadeguard.knowledge.loader import PROJECT_ROOT, load_clauses
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
        # Any word on binding force agrees with the clause: only a binding clause may be called
        # binding without "not" or "non-".
        if corpus[e.clause].binding is not True:
            for m in re.finditer(r"binding", e.relevance, re.IGNORECASE):
                before = e.relevance[: m.start()].lower()
                assert before.endswith(("not ", "non-")), e
    # The document states the mapping's state: a draft, or reviewed by the named human.
    text = committed(GAP_ANALYSIS)
    if examples.status == "draft":
        assert not any(e.approved for e in examples.entries)
        assert "DRAFT mapping awaiting the human's approval (gate 7)" in text
    else:
        assert examples.reviewed_by == "Ibrahim Melhem"  # gate 7, 2026-10-31
        assert "DRAFT" not in text
        assert (
            f"mapping reviewed by the human ({examples.reviewed_by}, {examples.reviewed_on}, "
            "gate 7)"
        ) in text
    # Rejected by the human (gate 7, 2026-10-31): never mapped again without a new decision.
    rejected = {"eu.gdpr.art33-1", "unesco.ai-ethics.responsibility-accountability"}
    assert not rejected & {e.clause for e in examples.entries}
    # Each example bullet shows its own entry's approval state.
    section = ""
    shown = 0
    for line in text.splitlines():
        if line.startswith("## `"):
            section = line.removeprefix("## `").removesuffix("`")
        m = re.match(
            r"^- `([a-z0-9.\-]+)` \[.*\((approved|DRAFT, not yet approved)\)\. Relevance:", line
        )
        if m:
            entry = next(e for e in examples.entries if e.failure == section and e.clause == m[1])
            assert (m[2] == "approved") is entry.approved, line
            shown += 1
    assert shown == len(examples.entries)


def test_gap_analysis_quotes_verbatim_and_keeps_every_qualification(runs: ScriptedRuns) -> None:
    text = committed(GAP_ANALYSIS)
    corpus = {c.id: c for c in load_clauses()}
    for f in runs.baseline.failures:
        assert f"## `{f.id}`" in text and f"_{f.qualification}_" in text
    header = "**Examples (context, not UAE law; UAE principles are not binding):**"
    assert text.count(header) == len(runs.baseline.failures)
    # Each clause bullet is followed by exactly its own clause text, in full and in order, and
    # carries its own status label.
    lines = text.splitlines()
    bullet = re.compile(r"^- `([a-z0-9.\-]+)` \[([^\]]+)\]")
    quoted = 0
    for i, line in enumerate(lines):
        m = bullet.match(line)
        if not m:
            continue
        cid, label = m.groups()
        assert label == corpus[cid].status_label, cid
        block: list[str] = []
        for nxt in lines[i + 1 :]:
            if not nxt.startswith("  >"):
                break
            block.append(nxt.removeprefix("  >").removeprefix(" "))
        if block:  # "Other loaded clauses" bullets carry no quote
            assert block == corpus[cid].text.strip().splitlines(), cid
            quoted += 1
    assert quoted >= len(runs.baseline.failures)


def test_a_failure_with_no_example_says_so(runs: ScriptedRuns) -> None:
    """Gate 7 (2026-10-31): a failure with no reviewed example keeps its section and states it,
    in the committed document and for any mapping that leaves a failure out."""
    from cascadeguard.storage.reports import NO_EXAMPLE, GapExamples, gap_analysis_markdown

    examples = load_gap_examples()
    mapped = {e.failure for e in examples.entries}
    unmapped = [f.id for f in runs.baseline.failures if f.id not in mapped]
    assert unmapped == ["orphan_duty:activate_fallback_channel"]
    text = committed(GAP_ANALYSIS)
    for fid in unmapped:
        section = text.split(f"## `{fid}`", 1)[1].split("\n## ", 1)[0]
        assert f"- {NO_EXAMPLE}" in section
    assert text.count(f"- {NO_EXAMPLE}") == len(unmapped)  # never in a section with examples
    # With no entries at all, every failure says so.
    corpus = {c.id: c for c in load_clauses()}
    empty = gap_analysis_markdown(runs, GapExamples(status="draft", entries=()), corpus)
    assert empty.count(f"- {NO_EXAMPLE}") == len(runs.baseline.failures)


def test_the_conclusion_draft_follows_the_human_rules(runs: ScriptedRuns) -> None:
    text = committed(CONCLUSION_DRAFT)
    assert text.startswith("# DRAFT conclusion wording (gate 7): not published")
    assert "unauthori" not in text.lower()
    # Twice per ungoverned run: the waived actions and the goal met at their minute.
    assert text.count(WITHOUT_AUTHORITY) == 4
    assert "met only in this run" not in text  # false: run 3 meets it too (gate 7)
    main, live = text.split("## Supporting evidence", 1)
    # The three scripted runs together, each labelled; governed vs ungoverned never alone.
    for run in ("**Governed** (", "**Ungoverned** (", "**Governed with the rank-1 repair** ("):
        assert f"{run}{SCRIPTED}" in main
    assert LIVE_LLM not in main and live.count(LIVE_LLM) == 2
    # Run 3's own paragraph states the removed and masked blockers and the authorization label.
    rep = runs.rank1
    run3 = main.split("3. **Governed with the rank-1 repair**", 1)[1].split("\n\n", 1)[0]
    assert len(rep.masked) == 2
    assert f"**Masked, cause still present:** {reports._ids(rep.masked)}." in run3  # pyright: ignore[reportPrivateUsage]
    assert f"Removed at their cause: {reports._ids(rep.removed)}." in run3  # pyright: ignore[reportPrivateUsage]
    assert rep.proposal.requires_authorization
    assert "no reviewed, binding clause in the loaded clause set supports" in run3
    assert rep.outcome == "resolved" and not rep.unmet_critical_goals
    # Gate-7 wording (2026-10-31): the outcome in words, and a plain-language repair label.
    assert (
        "Outcome: **all critical goals met (engine status: resolved). 2 failures removed at "
        "their cause, 2 masked with the cause still present**"
    ) in run3
    assert run3.startswith(
        " (scripted agents; replay of the identical incident). Make `health_service_operator` "
        "the owner of reversing automated lockouts within 30 minutes, and define a minimum share "
        "of network incident status from `telecom_operator` to `health_service_operator` (repair "
        f"`{rep.proposal.repair_id}`)"
    )
    run2 = main.split("2. **Ungoverned**", 1)[1].split("\n3. ", 1)[0]
    assert (
        "`patient_access_restored` is met in this run but not in the governed baseline, at "
        f"T+60, the minute an action was {WITHOUT_AUTHORITY}."
    ) in run2
    closing = main.split("The ungoverned run is shown only together", 1)[1]
    assert "governance off meets `patient_access_restored` by" in closing
    assert "alert_cause_known_to_health" not in closing
    # The live ungoverned bullet is followed directly by the repair result itself.
    bullets = [b for b in live.split("\n- ") if b.strip()]
    ungoverned = next(i for i, b in enumerate(bullets) if b.startswith("**Ungoverned**"))
    assert "but not in the live governed run, at T+15" in bullets[ungoverned]
    assert bullets[ungoverned + 1].startswith(
        "Repair result (scripted agents, run 3 above): all critical goals were met with the "
        "engine's checks in force, through two hypothetical policy edits that require "
        "institutional authorization."
    )
    # Every diagnosed failure list keeps its qualification, once per governed run.
    qualification = "a candidate gap for expert review, not a confirmed legal or standards gap"
    assert main.count(qualification) == 1 and live.count(qualification) == 1
    # No overstatement outside the fixed, negated phrases ("not ... a confirmed ... gap").
    free = text.replace("`", "").replace(reports.DISCLAIMER, "").replace(qualification, "")
    assert not OVERSTATED.search(free), OVERSTATED.findall(free)
    assert "No live repair replay was run" in live


def test_met_here_not_in_compares_with_the_named_baseline() -> None:
    from cascadeguard.storage.reports import met_here_not_in, newly_met

    waived = [{"minute": 60, "action": "x", "would_have_been_rejected": ["no_authority"]}]
    at_waived = met_here_not_in({"g": None}, {"g": 60}, waived, "governed baseline")
    elsewhere = met_here_not_in({"g": None}, {"g": 30}, waived, "live governed run")
    assert at_waived == (
        f"`g` is met in this run but not in the governed baseline, at T+60, the minute an "
        f"action was {WITHOUT_AUTHORITY}."
    )
    assert elsewhere == "`g` is met in this run but not in the live governed run, at T+30."
    assert met_here_not_in({"g": 10}, {"g": 60}, waived, "governed baseline") == ""
    assert newly_met({"a": None, "b": 5, "c": None}, {"a": 60, "b": 5, "c": None}) == ["a"]


def test_no_document_or_ui_links_the_draft() -> None:
    """Unpublished until the human approves it (gate 7): no Markdown file and no source file
    names it, except PROGRESS (the hand-off), the draft itself and its generator."""
    import subprocess

    # Every tracked text file; the structure file lists the project's files and is exempt.
    skip = {
        PROJECT_ROOT / "PROGRESS.md",
        PROJECT_ROOT / "cascadeguard_project_structure.txt",
        CONCLUSION_DRAFT,
        Path(reports.__file__).resolve(),
        Path(__file__).resolve(),
    }
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    text_suffixes = {".md", ".py", ".txt", ".yaml", ".yml", ".toml", ".json", ".css", ".html"}
    paths = [PROJECT_ROOT / name for name in tracked if Path(name).suffix in text_suffixes]
    checked = [p for p in paths if p.exists() and p.resolve() not in {s.resolve() for s in skip}]
    assert len(checked) > 20
    for path in checked:
        assert "pr5-conclusion-draft" not in path.read_text(encoding="utf-8"), path


def test_a_reviewed_mapping_needs_every_entry_approved() -> None:
    from datetime import date

    from pydantic import ValidationError

    from cascadeguard.storage.reports import GapExamples

    by, on = "Ibrahim Melhem", date(2026, 10, 31)
    entries = load_gap_examples().entries
    approved = tuple(e.model_copy(update={"approved": True}) for e in entries)
    one_draft = (approved[0].model_copy(update={"approved": False}), *approved[1:])
    with pytest.raises(ValidationError, match="every entry is approved"):
        GapExamples(status="reviewed", entries=one_draft, reviewed_by=by, reviewed_on=on)
    with pytest.raises(ValidationError, match="every entry is approved"):
        GapExamples(status="draft", entries=approved)
    with pytest.raises(ValidationError, match="every entry is approved"):
        GapExamples(status="reviewed", entries=(), reviewed_by=by, reviewed_on=on)
    with pytest.raises(ValidationError, match="names its reviewer and date"):
        GapExamples(status="reviewed", entries=approved)
    with pytest.raises(ValidationError, match="names its reviewer and date"):
        GapExamples(status="reviewed", entries=approved, reviewed_by=by)
    with pytest.raises(ValidationError, match="names its reviewer and date"):
        GapExamples(status="reviewed", entries=approved, reviewed_on=on)
    with pytest.raises(ValidationError, match="names its reviewer and date"):
        GapExamples(status="reviewed", entries=approved, reviewed_by=" ", reviewed_on=on)
    with pytest.raises(ValidationError, match="in the future"):
        GapExamples(
            status="reviewed", entries=approved, reviewed_by=by, reviewed_on=date(2999, 1, 1)
        )
    drafts = tuple(e.model_copy(update={"approved": False}) for e in entries)
    with pytest.raises(ValidationError, match="no reviewer or review date"):
        GapExamples(status="draft", entries=drafts, reviewed_by=by)
    with pytest.raises(ValidationError, match="mapped once"):
        GapExamples(status="draft", entries=(drafts[0], drafts[0]))
    assert (
        GapExamples(status="reviewed", entries=approved, reviewed_by=by, reviewed_on=on).status
        == "reviewed"
    )
    assert load_gap_examples().status == "reviewed"  # the committed file (gate 7)


def test_the_draft_claims_follow_the_data(runs: ScriptedRuns) -> None:
    from cascadeguard.storage.reports import load_gate4, same_failures, waived_actions

    live_base, _ = load_gate4()
    live = [f["id"] for f in live_base["failures"]]
    scripted = [f.id for f in runs.baseline.failures]
    assert sorted(live) == sorted(scripted)  # so the draft may say "the same"
    assert same_failures(live, scripted).startswith("the same")
    assert not same_failures(live[:1], scripted).startswith("the same")
    waived = [{"minute": 60, "action": "x", "would_have_been_rejected": ["missing_information"]}]
    with pytest.raises(ValueError, match="without an authority reason"):
        waived_actions(waived)


def test_outcome_and_closing_follow_any_ranked_repair(runs: ScriptedRuns) -> None:
    """The outcome text and the closing sentence are built from the repair, never fixed: checked
    on every ranked candidate, not only on the rank-1 repair."""
    from dataclasses import replace

    from cascadeguard.storage.reports import conclusion_markdown, load_gate4, outcome_text

    seen_unmet = seen_remaining = False
    for c in runs.search.ranked:
        text = outcome_text(c)
        assert f"(engine status: {c.outcome})" in text
        removed = len(c.removed)
        assert f"{removed} failure{'' if removed == 1 else 's'} removed at their cause" in text
        assert f"{len(c.masked)} masked with the cause still present" in text
        if c.remaining:
            seen_remaining = True
            assert f"{len(c.remaining)} still blocking" in text
        if c.unmet_critical_goals:
            seen_unmet = True
            assert text.startswith("critical goals unmet: ")
            draft = conclusion_markdown(replace(runs, rank1=c), load_gate4())
            closing = draft.split("The ungoverned run is shown only together", 1)[1]
            closing = closing.split("\n\n", 1)[0]
            assert "meets every critical goal" not in closing
            assert all(f"`{g}`" in closing for g in c.unmet_critical_goals)
            assert ("institutional approval" in closing) is c.proposal.requires_authorization
    assert seen_unmet and seen_remaining  # the search has partial candidates to check against
