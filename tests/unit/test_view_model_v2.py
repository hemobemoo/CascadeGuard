"""Demo UI v2 display rows (spec 006): formatting only, every label from engine constants."""

from dataclasses import replace
from typing import Any

import pytest

from cascadeguard.cli import World, load_world, search_repairs
from cascadeguard.domain.findings import FailureCategory
from cascadeguard.domain.repairs import RepairEdit, RepairOperationType, RepairProposal
from cascadeguard.engine.constraints import AGENT_STATEMENT, OBLIGATION_OVERDUE
from cascadeguard.engine.repair_search import (
    OPEN_AT_END_LABEL,
    ReplayComparison,
    SearchResult,
    outcome_text,
)
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.replay import REPAIR_LABEL, replay
from cascadeguard.ui import app
from cascadeguard.ui import view_model as vm

SCENARIO = "uae_health_access"
HEALTH = "health_service_operator"
TELECOM = "telecom_operator"
REVERSE = "reverse_automated_lockouts"
TOP = (
    "owner.reverse_automated_lockouts.health_service_operator.30m"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)


@pytest.fixture(scope="module")
def world() -> World:
    return load_world(SCENARIO)


@pytest.fixture(scope="module")
def found(world: World) -> SearchResult:
    return search_repairs(SCENARIO, world=world)


def test_verdict_strip(world: World, found: SearchResult) -> None:
    v = vm.verdict(world.baseline(), found, world.scenario)
    assert (v.critical, v.baseline_met, v.replay_met) == (2, 0, 2)
    assert v.baseline_failures == 4 and (v.removed, v.masked, v.remaining) == (2, 2, 0)
    assert v.repair_id == TOP and v.badge == vm.SMALLEST_SAFE
    assert v.outcome == outcome_text(found.ranked[0])  # engine wording, definition included
    empty = vm.verdict(world.baseline(), replace(found, ranked=()), world.scenario)
    assert empty.replay_met is None and empty.badge == "" and empty.repair_id == ""


def test_badge_only_on_a_clean_complete_resolved_rank_one(found: SearchResult) -> None:
    top, second = found.ranked[0], found.ranked[1]
    assert vm.badge(top, 1) == vm.SMALLEST_SAFE
    assert vm.badge(top, 2) == ""
    partial = next(c for c in found.ranked if c.outcome == "partial")
    assert vm.badge(partial, 1) == f"{vm.TOP_RANKED} (partial)"
    conflict = next(c for c in found.ranked if c.new_conflicts)
    assert vm.badge(conflict, 1) == f"{vm.TOP_RANKED} (introduces new conflict)"
    failed = replace(second, replay=replace(second.replay, failed_steps=((0, HEALTH, "x"),)))
    assert vm.badge(failed, 1).startswith(vm.TOP_RANKED)  # incomplete: never "smallest safe"


def test_ladder_rows(found: SearchResult) -> None:
    rungs = vm.ladder(found)
    assert [r.rank for r in rungs] == list(range(1, len(found.ranked) + 1))
    assert rungs[0].badge == vm.SMALLEST_SAFE and all(r.badge == "" for r in rungs[1:])
    assert rungs[0].roles == (HEALTH, TELECOM) and rungs[0].edits == 2
    assert rungs[0].authorization == vm.REQUIRES_AUTHORIZATION


def test_swimlanes_show_only_what_reached_each_role(world: World) -> None:
    base = world.baseline()
    lanes = {lane.role: lane for lane in vm.swimlanes(base, world.scenario)}
    assert list(lanes) == [r.id for r in world.roles.roles]
    boundary = dict(base.boundaries)
    for role, lane in lanes.items():
        assert [c.minute for c in lane.cells] == [e.at_minute for e in world.scenario.events]
        for c in lane.cells:
            assert all(f.label in boundary[role] for f in c.facts), role
            assert all(st.startswith(AGENT_STATEMENT) for st in c.statements)
    telecom_facts = {f.text for c in lanes[TELECOM].cells for f in c.facts}
    assert "locked_account_records" not in telecom_facts
    health = {c.minute: {f.text for f in c.facts} for c in lanes[HEALTH].cells}
    assert "otp_delivery_status" not in health[30]  # outside its boundary in the baseline
    released = {(e.role, e.detail) for e in base.log if e.kind == "fact_released"}
    shown = {(lane.role, f.text) for lane in lanes.values() for c in lane.cells for f in c.facts}
    assert shown == released


def test_obligation_bars_carry_source_labels_and_states(world: World, found: SearchResult) -> None:
    rep = found.comparison(TOP).replay
    lanes = {lane.role: lane for lane in vm.swimlanes(rep, world.scenario)}
    owner = next(b for b in lanes[HEALTH].bars if b.action == REVERSE)
    assert owner.source.label == REPAIR_LABEL and owner.source.css == "cg-status-repair"
    assert (owner.opened, owner.due, owner.state) == ("T+30", "T+60", "fulfilled at T+60")
    assert (owner.start, owner.end) == (2, 4)
    notify = next(b for b in lanes[HEALTH].bars if b.action == "notify_health_data_oversight")
    assert notify.due == "undetermined" and notify.end == len(world.scenario.events) - 1
    assert notify.source.label == dict(rep.loaded_clauses)["dha.pp11.4-18-4"]
    assert not [b for b in lanes[TELECOM].bars if b.action == REVERSE]


def _owner(deadline: int) -> RepairProposal:
    edits = (
        RepairEdit(
            operation=RepairOperationType.ASSIGN_OWNER,
            role=HEALTH,
            action=REVERSE,
            deadline_minutes=deadline,
        ),
        RepairEdit(
            operation=RepairOperationType.DEFINE_MINIMUM_DATA_SHARE,
            role=TELECOM,
            counterpart=HEALTH,
            data_category="network_incident_status",
        ),
    )
    ordered = tuple(sorted(edits, key=lambda e: e.edit_id))
    return RepairProposal(
        repair_id="+".join(e.edit_id for e in ordered), edits=ordered, rationale="t", citations=()
    )


def _no_reversal(world: World) -> dict[str, Any]:
    inner = world.agents[HEALTH]

    class NoReversal:
        def observe(self, view: RoleView) -> Any:
            d = inner.observe(view)
            kept = tuple(a for a in d.proposed_actions if a.action_type != REVERSE)
            return d.model_copy(update={"proposed_actions": kept})

    return {**world.agents, HEALTH: NoReversal()}


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (10, f"{OBLIGATION_OVERDUE} (due T+40)"),
        (46, OPEN_AT_END_LABEL.split(": ", 1)[0]),
    ],
)
def test_owner_bar_states_use_engine_labels(world: World, deadline: int, expected: str) -> None:
    rep = replay(
        world.scenario,
        world.roles,
        world.clauses,
        world.corpus_ids,
        _no_reversal(world),
        world.label,
        _owner(deadline),
    )
    lanes = {lane.role: lane for lane in vm.swimlanes(rep, world.scenario)}
    (bar,) = [b for b in lanes[HEALTH].bars if b.action == REVERSE]
    assert bar.state == expected


def test_open_at_end_state_word_comes_from_the_engine_label() -> None:
    assert vm.OPEN_AT_END_STATE == "open at incident end"
    assert vm.OPEN_AT_END_STATE in OPEN_AT_END_LABEL


def test_diagnosis_cards_cover_all_five_categories(world: World) -> None:
    base = world.baseline()
    cards = vm.diagnosis_cards(base)
    assert [c.category for c in cards] == [c.value for c in FailureCategory]
    items = {i.id: i for c in cards for i in c.items}
    assert set(items) == {f.id for f in base.failures}
    fallback = items["orphan_duty:activate_fallback_channel"]
    assert [(e.text, e.label) for e in fallback.evidence] == [
        ("dha.pp11.4-18-1", dict(base.loaded_clauses)["dha.pp11.4-18-1"])
    ]
    assert all(i.qualification for i in items.values())
    empty = {c.category for c in cards if not c.items}
    assert {"mandate_overlap", "temporal_infeasibility"} <= empty


@pytest.mark.parametrize(
    ("label", "css"),
    [
        ("reviewed", "cg-status-reviewed"),
        ("reviewed (interpreted)", "cg-status-reviewed-interpreted"),
        ("draft (interpreted)", "cg-status-draft"),
        ("illustrative", "cg-status-illustrative"),
        (REPAIR_LABEL, "cg-status-repair"),
        ("not loaded", "cg-status-none"),
    ],
)
def test_status_colours_are_fixed_and_keep_the_label(label: str, css: str) -> None:
    assert vm.status_class(label) == css
    (chip,) = vm.clause_chips(["x"], {"x": label})
    assert chip.label == label and chip.css == css


def _llm_like(c: ReplayComparison, outcome_from: ReplayComparison) -> ReplayComparison:
    """A comparison whose outcome is that of another one (stands in for an LLM replay)."""
    return replace(c, replay=outcome_from.replay)


def test_scripted_vs_llm_shows_a_finding_only_when_the_verdicts_match(found: SearchResult) -> None:
    top = found.comparison(TOP)
    partial = next(c for c in found.ranked if c.outcome == "partial")
    llm = _llm_like(top, partial)
    assert llm.outcome == "partial"
    recorded = app.findings_for(SCENARIO)
    assert len(recorded) == 1 and recorded[0].repair == TOP
    row = vm.scripted_vs_llm(top, llm, "phase5-v4+json_object", recorded)
    assert row.scripted == outcome_text(top) and row.llm == outcome_text(llm)
    assert "did not act within it" in row.finding
    assert row.source == "docs/evaluation/adr-0002-golden-llm-replay.md"
    # Any other prompt version (exact match, mode and options included), or a verdict that no
    # longer matches: nothing is shown.
    for version in (
        "phase5-v3+json_object",
        "phase5-v4",
        "phase5-v40+json_object",
        "phase5-v4+json_schema",
        "phase5-v4+json_object+extracted",
    ):
        assert vm.scripted_vs_llm(top, llm, version, recorded).finding == "", version
    assert vm.scripted_vs_llm(top, top, "phase5-v4+json_object", recorded).finding == ""
    # Two different repairs are never compared.
    with pytest.raises(ValueError, match="same repair"):
        vm.scripted_vs_llm(found.ranked[1], llm, "phase5-v4+json_object", recorded)


def test_evaluation_findings_file_is_validated(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / SCENARIO).mkdir()
    bad = tmp_path / SCENARIO / "evaluation_findings.yaml"
    monkeypatch.setattr(app, "SCENARIOS_DIR", tmp_path)
    assert app.findings_for(SCENARIO) == ()  # no file: no findings
    bad.write_text("findings:\n  - repair: x\n    text: y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly the text fields"):
        app.findings_for(SCENARIO)
    fields = "repair: x\n    prompt_version: v\n    scripted: a\n    llm: b\n    text: t\n"
    bad.write_text(f"findings:\n  - {fields}    source: s\n    extra: z\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly the text fields"):
        app.findings_for(SCENARIO)
    bad.write_text(f"findings:\n  - {fields}    source: 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly the text fields"):
        app.findings_for(SCENARIO)


def test_verdict_shows_the_baseline_caveat_even_with_nothing_ranked(
    world: World, found: SearchResult
) -> None:
    base = replace(world.baseline(), invalid_steps=((15, TELECOM),))
    for search_result in (found, replace(found, ranked=())):
        v = vm.verdict(base, search_result, world.scenario)
        assert v.caveat == (
            "1 steps with no decision (model returned invalid output): telecom_operator at T+15 "
            "(baseline); the result may depend on them"
        )
    assert vm.verdict(world.baseline(), found, world.scenario).caveat == ""


def test_app_shows_engine_labels_not_typed_copies() -> None:
    from pathlib import Path

    source = Path(app.__file__).read_text(encoding="utf-8")
    for typed in (
        '"removed at their cause"',
        '"masked (goal met another way)"',
        '"agent statement"',
        "Inconclusive (unranked",
    ):
        assert typed not in source, typed
    assert app.STATEMENT == "agent statement"


def test_ui_has_no_live_llm_mode() -> None:
    assert set(app.AGENT_MODES) == {"scripted", "llm-offline"}
    assert app.agent_choice("llm-offline").offline
    assert "live" not in " ".join(app.AGENT_MODES.values()).lower()


def test_html_blocks_escape_untrusted_text() -> None:
    hostile = '"><img src=x onerror=alert(1)><script>x</script>'
    out = app.esc(hostile)
    assert "<" not in out and ">" not in out and '"' not in out
    chip = app.chip_html(vm.Chip(hostile, hostile, '" onclick="x'))
    assert "<img" not in chip and "<script" not in chip and 'onclick="x' not in chip
