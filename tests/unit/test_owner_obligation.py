"""ADR 0002 option A (human decision 2026-10-26): an owner repair opens an obligation for the
owner once it holds network_incident_status and the automated lockouts are in place; views list
each role's open obligations; a missed deadline is the finding obligation_overdue at exactly
opened_at + deadline and keeps the orphan duty as a remaining blocker."""

import json
from typing import Any

import pytest

from cascadeguard.agents.cache import cache_key
from cascadeguard.agents.llm import PROMPT_VERSION, SYSTEM_PROMPT, render_view, response_schema
from cascadeguard.cli import World, load_world
from cascadeguard.domain.findings import FailureCategory
from cascadeguard.domain.repairs import (
    OWNER_DEADLINE_MINUTES,
    REPAIR_LABEL,
    RepairEdit,
    RepairOperationType,
    RepairProposal,
)
from cascadeguard.domain.scenario import Scenario
from cascadeguard.engine.constraints import OBLIGATION_OVERDUE, ConstraintEngine
from cascadeguard.engine.repair_search import ReplayComparison, rank_key
from cascadeguard.simulation.boundaries import RoleView, view_for
from cascadeguard.simulation.orchestrator import RunResult, run
from cascadeguard.simulation.replay import repair_clause_id, replay
from cascadeguard.simulation.state import SimulationState

HEALTH = "health_service_operator"
TELECOM = "telecom_operator"
REVERSE = "reverse_automated_lockouts"
CRITICAL = ("patient_access_restored", "alert_cause_known_to_health")


def owner(deadline: int | None = None) -> RepairEdit:
    extra: dict[str, Any] = {} if deadline is None else {"deadline_minutes": deadline}
    return RepairEdit(
        operation=RepairOperationType.ASSIGN_OWNER, role=HEALTH, action=REVERSE, **extra
    )


SHARE = RepairEdit(
    operation=RepairOperationType.DEFINE_MINIMUM_DATA_SHARE,
    role=TELECOM,
    counterpart=HEALTH,
    data_category="network_incident_status",
)


def proposal(*edits: RepairEdit) -> RepairProposal:
    ordered = tuple(sorted(edits, key=lambda e: e.edit_id))
    return RepairProposal(
        repair_id="+".join(e.edit_id for e in ordered),
        edits=ordered,
        rationale="test",
        citations=(),
    )


@pytest.fixture(scope="module")
def world() -> World:
    return load_world("uae_health_access")


def replayed(w: World, p: RepairProposal, scenario: Scenario | None = None) -> RunResult:
    return replay(scenario or w.scenario, w.roles, w.clauses, w.corpus_ids, w.agents, w.label, p)


def owner_obligations(result: RunResult) -> list[Any]:
    return [o for o in result.obligations if o.clause_id.startswith("repair.owner.")]


# --- The repair edit ------------------------------------------------------------------------


def test_owner_deadline_defaults_to_30_and_is_part_of_the_id() -> None:
    assert owner().deadline_minutes == OWNER_DEADLINE_MINUTES == 30
    assert owner().edit_id == "owner.reverse_automated_lockouts.health_service_operator.30m"
    assert owner(10).edit_id.endswith(".10m")
    assert owner(10).edit_id != owner().edit_id
    with pytest.raises(ValueError):
        RepairEdit.model_validate(
            {
                "operation": "assign_owner",
                "role": HEALTH,
                "action": REVERSE,
                "deadline_minutes": "30",
            }
        )


# --- When the obligation opens --------------------------------------------------------------


def test_opens_at_the_first_step_where_both_conditions_hold(world: World) -> None:
    result = replayed(world, proposal(owner(), SHARE))
    (ob,) = owner_obligations(result)
    # The status reaches the operator at T+30 (widened boundary); the locks are in place since
    # T+15. Due 30 minutes later; the scripted reversal at T+60 is on time.
    assert (ob.role, ob.action, ob.opened_at, ob.due_at) == (HEALTH, REVERSE, 30, 60)
    assert ob.fulfilled_at == 60 and not ob.missed
    assert not [f for f in result.findings if f.kind == OBLIGATION_OVERDUE]
    opened = [e for e in result.log if e.kind == "obligation_opened" and e.action == REVERSE]
    assert [(e.minute, e.clause_ids) for e in opened] == [(30, (repair_clause_id(owner()),))]


def test_never_opens_in_the_owner_only_replay(world: World) -> None:
    result = replayed(world, proposal(owner()))
    assert owner_obligations(result) == []
    assert not [e for e in result.log if e.kind == "obligation_opened" and e.action == REVERSE]
    assert all(not o.source.startswith("repair.") for v in result.views for o in v.open_obligations)


def test_never_opens_without_the_lockouts(world: World) -> None:
    """The status arrives, but no lock records were ever released: not in place."""
    events = tuple(
        e.model_copy(
            update={
                "facts": tuple(f for f in e.facts if f.data_category != "patient_account_records")
            }
        )
        for e in world.scenario.events
    )
    result = replayed(
        world, proposal(owner(), SHARE), world.scenario.model_copy(update={"events": events})
    )
    assert any(f.data_category == "network_incident_status" for v in result.views for f in v.facts)
    assert owner_obligations(result) == []


def test_opens_after_an_accepted_share_in_the_same_step(world: World) -> None:
    """Checked after every accepted action too: here the health operator is not a recipient of
    the T+30 inject, so the status arrives only through the telecom operator's share."""
    events = tuple(
        e.model_copy(update={"recipients": (TELECOM,)}) if e.at_minute == 30 else e
        for e in world.scenario.events
    )
    result = replayed(
        world, proposal(owner(), SHARE), world.scenario.model_copy(update={"events": events})
    )
    (ob,) = owner_obligations(result)
    assert ob.opened_at == 30
    share = next(
        e
        for e in result.log
        if e.kind == "accepted" and e.action == "share_incident_status" and e.target == HEALTH
    )
    opened = next(e for e in result.log if e.kind == "obligation_opened" and e.action == REVERSE)
    assert share.minute == 30 and share.seq < opened.seq


def engine_world(w: World) -> tuple[SimulationState, ConstraintEngine]:
    from cascadeguard.simulation.replay import apply_repair

    s, r, c = apply_repair(w.scenario, w.roles, w.clauses, proposal(owner(), SHARE))
    state = SimulationState(s, r)
    return state, ConstraintEngine(state, dict(c), w.corpus_ids)


def test_never_opens_once_the_lockouts_were_reversed(world: World) -> None:
    """In place means not yet reversed: a reversal before the evidence arrives means no
    obligation."""
    state, engine = engine_world(world)
    events = state.scenario.events
    engine.release(events[0])
    engine.release(events[1])
    state.mark_done(HEALTH, REVERSE)  # the locks were reversed before T+30
    engine.release(events[2])
    assert state.has_seen_category(HEALTH, "network_incident_status")
    assert [o for o in state.obligations if o.action == REVERSE] == []


def test_each_condition_alone_does_not_open_it(world: World) -> None:
    state, engine = engine_world(world)
    events = state.scenario.events
    engine.release(events[0])
    engine.release(events[1])  # locks in place, no status yet
    assert [o for o in state.obligations if o.action == REVERSE] == []
    engine.release(events[2])  # now both
    assert [o.opened_at for o in state.obligations if o.action == REVERSE] == [30]
    engine.release(events[3])
    assert len([o for o in state.obligations if o.action == REVERSE]) == 1  # opens once


def test_an_action_without_a_condition_opens_no_owner_obligation(world: World) -> None:
    roles = world.roles.model_copy(
        update={
            "actions": tuple(
                a.model_copy(update={"owner_obligation_opens_when": None}) if a.id == REVERSE else a
                for a in world.roles.actions
            )
        }
    )
    result = replay(
        world.scenario,
        roles,
        world.clauses,
        world.corpus_ids,
        world.agents,
        world.label,
        proposal(owner(), SHARE),
    )
    assert owner_obligations(result) == []


# --- Overdue ---------------------------------------------------------------------------------


@pytest.mark.parametrize("deadline", [10, 15, 29])
def test_overdue_finding_at_exactly_opened_at_plus_deadline(world: World, deadline: int) -> None:
    result = replayed(world, proposal(owner(deadline), SHARE))
    (ob,) = owner_obligations(result)
    assert ob.missed and ob.due_at == 30 + deadline
    (finding,) = [f for f in result.findings if f.kind == OBLIGATION_OVERDUE]
    assert finding.minute == ob.opened_at + deadline
    assert (finding.role, finding.clause_ids) == (HEALTH, (repair_clause_id(owner(deadline)),))


def test_fulfilled_exactly_at_the_deadline_is_not_overdue(world: World) -> None:
    result = replayed(world, proposal(owner(30), SHARE))  # due T+60, reversed at T+60
    assert not [f for f in result.findings if f.kind == OBLIGATION_OVERDUE]


def test_overdue_keeps_the_orphan_duty_as_a_remaining_blocker(world: World) -> None:
    baseline = world.baseline()
    late = ReplayComparison(
        proposal(owner(10), SHARE), baseline, replayed(world, proposal(owner(10), SHARE)), CRITICAL
    )
    on_time = ReplayComparison(
        proposal(owner(), SHARE), baseline, replayed(world, proposal(owner(), SHARE)), CRITICAL
    )
    orphan = f"{FailureCategory.ORPHAN_DUTY.value}:{REVERSE}"
    assert late.overdue == (REVERSE,)
    assert orphan in late.remaining
    assert orphan not in late.removed and orphan not in late.masked
    assert orphan in on_time.removed and on_time.overdue == ()
    # Not a new temporal-infeasibility conflict; it is not discarded.
    assert late.new_conflicts == ()
    assert not any(
        f.category is FailureCategory.TEMPORAL_INFEASIBILITY for f in late.replay.failures
    )
    assert late.critical_blockers_removed == on_time.critical_blockers_removed - 1
    assert rank_key(on_time) < rank_key(late)
    assert late.summary()["obligations_overdue"] == [REVERSE]
    assert "obligations_overdue" not in on_time.summary()


def test_overdue_obligation_is_shown_as_overdue_until_fulfilled(world: World) -> None:
    result = replayed(world, proposal(owner(10), SHARE))
    status = {
        v.minute: [o.status for o in v.open_obligations if o.action == REVERSE]
        for v in result.views
        if v.role_id == HEALTH
    }
    # Opened at T+30 (open), due T+40: overdue at T+45 and T+60; fulfilled at T+60 (late).
    assert status == {0: [], 15: [], 30: ["open"], 45: ["overdue"], 60: ["overdue"], 75: []}


# --- Views ------------------------------------------------------------------------------------


def test_views_show_only_the_roles_own_obligations(world: World) -> None:
    for result in (world.baseline(), replayed(world, proposal(owner(), SHARE))):
        for v in result.views:
            mine = [
                o
                for o in result.obligations
                if o.role in (v.role_id, "any")
                and o.opened_at <= v.minute
                and (o.fulfilled_at is None or o.fulfilled_at >= v.minute)
            ]
            assert {o.source for o in v.open_obligations} <= {o.clause_id for o in mine}
            others = {o.clause_id for o in result.obligations if o.role not in (v.role_id, "any")}
            assert not {o.source for o in v.open_obligations} & others
    rep = replayed(world, proposal(owner(), SHARE))
    holders = {v.role_id for v in rep.views for o in v.open_obligations if o.action == REVERSE}
    assert holders == {HEALTH}
    telecom = {o.source for v in rep.views if v.role_id == TELECOM for o in v.open_obligations}
    assert telecom == {"illus.telecom.incident-report"}


def test_view_lists_obligations_on_any_role_and_their_labels(world: World) -> None:
    state, _ = engine_world(world)
    clauses = dict(world.clauses)
    state.open_obligation("dha.pp11.4-18-2", "any", "raise_security_incident", None)
    state.open_obligation(repair_clause_id(owner()), HEALTH, REVERSE, 30)
    event = state.scenario.events[0]
    for role in (HEALTH, TELECOM):
        listed = view_for(state, role, event, clauses, world.corpus_ids).open_obligations
        assert "dha.pp11.4-18-2" in {o.source for o in listed}
    health = {
        o.source: o
        for o in view_for(state, HEALTH, event, clauses, world.corpus_ids).open_obligations
    }
    assert health[repair_clause_id(owner())].source_label == REPAIR_LABEL
    assert health["dha.pp11.4-18-2"].source_label == clauses["dha.pp11.4-18-2"].status_label
    assert health["dha.pp11.4-18-2"].due_at is None
    telecom = view_for(state, TELECOM, event, clauses, world.corpus_ids).open_obligations
    assert repair_clause_id(owner()) not in {o.source for o in telecom}


def test_views_are_frozen_copies() -> None:
    from dataclasses import FrozenInstanceError

    from cascadeguard.simulation.boundaries import OpenObligation

    o = OpenObligation("x@T+00", "a", "x", "illustrative", 0, None, "open")
    with pytest.raises(FrozenInstanceError):
        o.status = "fulfilled"  # type: ignore[misc]


# --- Prompt and cache ---------------------------------------------------------------------------


def health_view_at(result: RunResult, minute: int) -> RoleView:
    return next(v for v in result.views if v.role_id == HEALTH and v.minute == minute)


def test_prompt_contains_the_roles_open_obligations(world: World) -> None:
    view = health_view_at(replayed(world, proposal(owner(), SHARE)), 30)
    data = json.loads(render_view(view, tuple(r.id for r in world.roles.roles)))
    rule = repair_clause_id(owner())
    assert {
        "id": f"{rule}@T+30",
        "action": REVERSE,
        "source": rule,
        "source_status": REPAIR_LABEL,
        "opened_at": "T+30",
        "due_at": "T+60",
        "status": "open",
    } in data["your_open_obligations"]
    notify = next(o for o in data["your_open_obligations"] if o["source"] == "dha.pp11.4-18-4")
    assert notify["due_at"] == "undetermined"
    # Only the data is shown: the system prompt gives no instruction about obligations.
    assert "obligation" not in SYSTEM_PROMPT.lower()


def test_cache_key_changes_with_the_prompt_version_and_the_obligations(world: World) -> None:
    rep = replayed(world, proposal(owner(), SHARE))
    view = health_view_at(rep, 30)
    schema = response_schema()
    v4 = cache_key(HEALTH, view, PROMPT_VERSION, "test/fake-model", schema)
    assert PROMPT_VERSION == "phase5-v4"
    assert cache_key(HEALTH, view, "phase5-v3", "test/fake-model", schema) != v4
    from dataclasses import replace

    without = replace(view, open_obligations=())
    assert cache_key(HEALTH, without, PROMPT_VERSION, "test/fake-model", schema) != v4


def test_runs_stay_deterministic(world: World) -> None:
    p = proposal(owner(10), SHARE)
    a, b = replayed(world, p), replayed(world, p)
    assert a.summary() == b.summary() and a.views == b.views


def test_run_without_repair_has_no_owner_obligations(world: World) -> None:
    result = run(
        world.scenario, world.roles, world.clauses, world.corpus_ids, world.agents, world.label
    )
    assert world.scenario.owner_obligations == ()
    assert owner_obligations(result) == []


# --- Display: UI role view, comparison rows, Markdown and CLI ---------------------------------


def comparisons(world: World) -> tuple[ReplayComparison, ReplayComparison]:
    baseline = world.baseline()
    late, on_time = proposal(owner(10), SHARE), proposal(owner(), SHARE)
    return (
        ReplayComparison(late, baseline, replayed(world, late), CRITICAL),
        ReplayComparison(on_time, baseline, replayed(world, on_time), CRITICAL),
    )


def test_ui_role_view_lists_open_obligations_with_labels_and_deadlines(world: World) -> None:
    from cascadeguard.ui import view_model as vm

    result = replayed(world, proposal(owner(10), SHARE))
    categories = world.roles.known_categories()
    rule = repair_clause_id(owner(10))
    at30 = vm.role_view(result, HEALTH, 30, categories).open_obligations
    assert f"{REVERSE} (open): opened T+30, due T+40; {rule} [{REPAIR_LABEL}]" in at30
    label = world.clauses["dha.pp11.4-18-4"].status_label
    assert (
        f"notify_health_data_oversight (open): opened T+15, due undetermined; "
        f"dha.pp11.4-18-4 [{label}]"
    ) in at30
    at45 = vm.role_view(result, HEALTH, 45, categories).open_obligations
    assert f"{REVERSE} (overdue): opened T+30, due T+40; {rule} [{REPAIR_LABEL}]" in at45
    telecom = vm.role_view(result, TELECOM, 30, categories).open_obligations
    assert not [row for row in telecom if REVERSE in row]


def test_overdue_blocker_is_explained_in_markdown_cli_and_ui(world: World) -> None:
    from cascadeguard.cli import format_search
    from cascadeguard.engine.repair_search import OVERDUE_LABEL, SearchResult
    from cascadeguard.storage.export import comparison_markdown
    from cascadeguard.ui import view_model as vm

    late, on_time = comparisons(world)
    orphan = f"orphan_duty:{REVERSE}"
    assert late.overdue_blockers == (orphan,) and on_time.overdue_blockers == ()
    from cascadeguard.engine.repair_search import outcome_text

    assert "1 remaining: owner obligation overdue" in outcome_text(late)
    assert "owner obligation overdue" not in outcome_text(on_time)
    assert OVERDUE_LABEL in comparison_markdown(late)
    assert OVERDUE_LABEL not in comparison_markdown(on_time)
    assert f"{orphan}: remaining [{OVERDUE_LABEL}]" in vm.comparison(late).replay_failures
    assert not [r for r in vm.comparison(on_time).replay_failures if OVERDUE_LABEL in r]

    def search_text(c: ReplayComparison) -> str:
        return format_search(
            SearchResult(c.baseline.clause_set, c.baseline.loaded_clauses, (c,), ())
        )

    assert f"{OVERDUE_LABEL}: {orphan}" in search_text(late)
    assert OVERDUE_LABEL not in search_text(on_time)


# --- Test-breaker round 1 (MINORs) -------------------------------------------------------------


def test_scenario_yaml_may_not_set_owner_obligations(tmp_path: Any) -> None:
    import shutil

    from cascadeguard.simulation.loader import SCENARIOS_DIR, ScenarioLoadError, load_scenario

    target = tmp_path / "uae_health_access"
    shutil.copytree(SCENARIOS_DIR / "uae_health_access", target)
    yaml_file = target / "scenario.yaml"
    yaml_file.write_text(
        yaml_file.read_text(encoding="utf-8") + "owner_obligations: [repair.x]\n", encoding="utf-8"
    )
    with pytest.raises(ScenarioLoadError, match="owner_obligations"):
        load_scenario("uae_health_access", set(), tmp_path)


def test_only_owner_rules_get_the_owner_treatment(world: World) -> None:
    """A non-owner rule listed in owner_obligations is still a temporal-infeasibility conflict
    when missed, and is never opened by the owner condition."""
    requester = RepairEdit(
        operation=RepairOperationType.DESIGNATE_DECISION_REQUESTER,
        role=HEALTH,
        action="activate_fallback_channel",
        counterpart="health_data_oversight",
        trigger_event="t60_public_access_affected",
        deadline_minutes=15,
    )
    p = proposal(requester, SHARE)
    from cascadeguard.simulation.replay import apply_repair

    s, r, c = apply_repair(world.scenario, world.roles, world.clauses, p)
    forged = s.model_copy(update={"owner_obligations": (repair_clause_id(requester),)})
    result = run(forged, r, c, world.corpus_ids, world.agents, world.label)
    missed = [o for o in result.obligations if o.clause_id == repair_clause_id(requester)]
    assert missed and missed[0].missed
    assert "temporal_infeasibility:request_determination" in {f.id for f in result.failures}
    assert not [f for f in result.findings if f.kind == OBLIGATION_OVERDUE]


def test_an_overdue_blocker_is_never_counted_as_masked(world: World) -> None:
    from dataclasses import replace

    late, _ = comparisons(world)
    orphan = next(f for f in late.baseline.failures if f.id == f"orphan_duty:{REVERSE}")
    # Its cause still present while it no longer blocks: would read as masked without the rule.
    forced = replace(late, replay=replace(late.replay, causes=(*late.replay.causes, orphan)))
    assert orphan.id not in forced.masked
    assert orphan.id in forced.remaining


def test_owner_condition_categories_must_be_scenario_categories(world: World) -> None:
    from cascadeguard.domain.scenario import RoleSet

    data = world.roles.model_dump(mode="python")
    for action in data["actions"]:
        if action["id"] == REVERSE:
            action["owner_obligation_opens_when"]["in_place"] = ["no_such_category"]
    with pytest.raises(ValueError, match="unknown condition categories"):
        RoleSet.model_validate(data)
    for action in data["actions"]:
        if action["id"] == REVERSE:
            action["owner_obligation_opens_when"]["in_place"] = []
    with pytest.raises(ValueError):
        RoleSet.model_validate(data)


# --- Open at incident end (human decision 2026-10-26) ---------------------------------------


def without_reversal(world: World) -> dict[str, Any]:
    """The scripted agents, except that the health operator never proposes the reversal."""
    inner = world.agents[HEALTH]

    class NoReversal:
        def observe(self, view: RoleView) -> Any:
            d = inner.observe(view)
            kept = tuple(a for a in d.proposed_actions if a.action_type != REVERSE)
            return d.model_copy(update={"proposed_actions": kept})

    return {**world.agents, HEALTH: NoReversal()}


def test_obligation_open_at_incident_end_keeps_its_orphan_duty_remaining(world: World) -> None:
    from cascadeguard.cli import format_search
    from cascadeguard.engine.repair_search import (
        OPEN_AT_END_LABEL,
        OVERDUE_LABEL,
        SearchResult,
        outcome_text,
    )
    from cascadeguard.storage.export import comparison_markdown
    from cascadeguard.ui import view_model as vm

    p = proposal(owner(46), SHARE)  # opens T+30, due T+76: after the last inject (T+75)
    rep = replay(
        world.scenario,
        world.roles,
        world.clauses,
        world.corpus_ids,
        without_reversal(world),
        world.label,
        p,
    )
    (ob,) = owner_obligations(rep)
    assert (ob.opened_at, ob.due_at, ob.fulfilled_at, ob.missed) == (30, 76, None, False)
    assert not [f for f in rep.findings if f.kind == OBLIGATION_OVERDUE]  # deadline not passed
    c = ReplayComparison(p, world.baseline(), rep, CRITICAL)
    orphan = f"orphan_duty:{REVERSE}"
    assert c.open_at_end == (REVERSE,) and c.overdue == ()
    assert c.open_at_end_blockers == (orphan,)
    assert orphan in c.remaining and orphan not in c.removed and orphan not in c.masked
    assert c.summary()["obligations_open_at_end"] == [REVERSE]
    assert "obligations_overdue" not in c.summary()
    assert "1 remaining: owner obligation open at incident end" in outcome_text(c)
    md = comparison_markdown(c)
    assert OPEN_AT_END_LABEL in md and OVERDUE_LABEL not in md
    assert f"{orphan}: remaining [{OPEN_AT_END_LABEL}]" in vm.comparison(c).replay_failures
    text = format_search(SearchResult(c.baseline.clause_set, c.baseline.loaded_clauses, (c,), ()))
    assert f"{OPEN_AT_END_LABEL}: {orphan}" in text
    # Same deadline, but the owner acts: fulfilled, so nothing is open at the end.
    acted = ReplayComparison(p, world.baseline(), replayed(world, p), CRITICAL)
    assert acted.open_at_end == () and orphan in acted.removed


def test_overdue_and_open_at_end_are_distinct(world: World) -> None:
    p = proposal(owner(10), SHARE)
    rep = replay(
        world.scenario,
        world.roles,
        world.clauses,
        world.corpus_ids,
        without_reversal(world),
        world.label,
        p,
    )
    c = ReplayComparison(p, world.baseline(), rep, CRITICAL)
    assert c.overdue == (REVERSE,) and c.open_at_end == ()  # missed, so overdue only
