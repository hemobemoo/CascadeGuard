"""--governance off waives only the clause and mandate checks (human decision 2026-10-31, B).

Role permissions, information boundaries, integrity and evidence checks reject in both modes.
"""

import pytest

from cascadeguard.domain.decisions import AgentDecision, Citation, ProposedAction
from cascadeguard.domain.policies import ClauseStatus
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import (
    WAIVABLE,
    WOULD_HAVE_BEEN_REJECTED,
    ConstraintEngine,
    Governance,
    Reason,
)
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.loader import load_scenario
from cascadeguard.simulation.state import SimulationState

HEALTH, TELECOM = "health_service_operator", "telecom_operator"


@pytest.fixture(scope="module")
def world() -> tuple[Scenario, RoleSet]:
    return load_scenario("uae_health_access", {c.id for c in load_clauses()})


def engine_at(
    world: tuple[Scenario, RoleSet], minute: int, governance: Governance
) -> ConstraintEngine:
    scenario, roles = world
    engine = ConstraintEngine(
        SimulationState(scenario, roles),
        load_engine_clauses(),
        frozenset(c.id for c in load_clauses()),
        governance,
    )
    for event in scenario.events:
        if event.at_minute <= minute:
            engine.release(event)
    return engine


def decide(
    world: tuple[Scenario, RoleSet],
    role: str,
    *actions: ProposedAction,
    rationale: str = "synthetic test decision",
    cites: tuple[str, ...] = (),
) -> AgentDecision:
    return AgentDecision(
        role_id=role,
        at=world[0].time_at(60),
        proposed_actions=actions,
        rationale=rationale,
        citations=tuple(Citation(clause_id=c, relevance="synthetic test") for c in cites),
        uncertainty=(),
    )


def last_verdicts(engine: ConstraintEngine) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    return [
        (e.kind, e.reasons, e.waived)
        for e in engine.state.log
        if e.kind in ("accepted", "rejected") and e.minute == 60
    ]


def test_the_default_is_governed(world: tuple[Scenario, RoleSet]) -> None:
    scenario, roles = world
    engine = ConstraintEngine(SimulationState(scenario, roles), {}, frozenset())
    assert engine.governance is Governance.ON


def test_waivable_reasons_are_exactly_the_clause_and_mandate_checks() -> None:
    assert {r.value for r in WAIVABLE} == {
        "no_authority",
        "authority_uncertain",
        "restricted_by_clause",
        "missing_prerequisite",
        "missing_information",
    }


@pytest.mark.parametrize("governance", list(Governance))
def test_a_waivable_rejection_is_applied_only_with_governance_off(
    world: tuple[Scenario, RoleSet], governance: Governance
) -> None:
    engine = engine_at(world, 60, governance)
    reverse = ProposedAction(action_type="reverse_automated_lockouts")
    engine.process(decide(world, HEALTH, reverse), expected_role=HEALTH)
    entry = [
        e
        for e in engine.state.log
        if e.kind in ("accepted", "rejected") and e.action == "reverse_automated_lockouts"
    ][-1]
    reasons = ("missing_prerequisite", "missing_information", "no_authority")
    if governance is Governance.ON:
        assert (entry.kind, entry.reasons, entry.waived) == ("rejected", reasons, ())
        assert not engine.state.has_done(HEALTH, "reverse_automated_lockouts")
    else:
        assert (entry.kind, entry.reasons, entry.waived) == ("accepted", (), reasons)
        assert entry.detail.startswith(WOULD_HAVE_BEEN_REJECTED + ", ".join(reasons) + "; ")
        assert engine.state.has_done(HEALTH, "reverse_automated_lockouts")


def test_role_permissions_still_reject(world: tuple[Scenario, RoleSet]) -> None:
    engine = engine_at(world, 60, Governance.OFF)
    action = ProposedAction(action_type="reverse_automated_lockouts")  # not a telecom action
    engine.process(decide(world, TELECOM, action), expected_role=TELECOM)
    assert last_verdicts(engine) == [("rejected", (Reason.NOT_ALLOWED_ACTION,), ())]
    assert not engine.state.has_done(TELECOM, "reverse_automated_lockouts")


def test_the_recipient_boundary_still_rejects_and_releases_nothing(
    world: tuple[Scenario, RoleSet],
) -> None:
    """A share outside the recipient's boundary stays rejected with all its reasons, the
    waivable ones included, exactly as when governed."""
    governed, ungoverned = engine_at(world, 60, Governance.ON), engine_at(world, 60, Governance.OFF)
    share = ProposedAction(
        action_type="share_incident_status",
        target=TELECOM,
        parameters={"fact": "locked_account_records"},
    )
    for engine in (governed, ungoverned):
        engine.process(decide(world, HEALTH, share), expected_role=HEALTH)
    assert last_verdicts(ungoverned) == last_verdicts(governed)
    kind, reasons, waived = last_verdicts(ungoverned)[0]
    assert kind == "rejected" and Reason.OUTSIDE_RECIPIENT_BOUNDARY in reasons and waived == ()
    assert "locked_account_records" not in {f.id for f in ungoverned.state.known_facts(TELECOM)}


@pytest.mark.parametrize(
    ("action", "reason"),
    [
        (ProposedAction(action_type="request_information", target="nobody"), "unknown_target"),
        (ProposedAction(action_type="request_information", target=HEALTH), "self_target"),
        (
            ProposedAction(action_type="request_information", target=TELECOM),
            "missing_parameter",
        ),
        (
            ProposedAction(
                action_type="share_incident_status",
                target=TELECOM,
                parameters={"fact": "not_a_fact"},
            ),
            "fact_not_known",
        ),
    ],
)
def test_integrity_checks_still_reject(
    world: tuple[Scenario, RoleSet], action: ProposedAction, reason: str
) -> None:
    engine = engine_at(world, 60, Governance.OFF)
    engine.process(decide(world, HEALTH, action), expected_role=HEALTH)
    assert last_verdicts(engine) == [("rejected", (reason,), ())]


def test_evidence_checks_still_reject_the_whole_decision(world: tuple[Scenario, RoleSet]) -> None:
    draft = next(c.id for c in load_clauses() if c.status is ClauseStatus.DRAFT)
    reverse = ProposedAction(action_type="reverse_automated_lockouts")
    cases = (
        (decide(world, HEALTH, reverse, cites=(draft,)), Reason.DRAFT_CITATION),
        (decide(world, HEALTH, reverse, cites=("no.such.clause",)), Reason.UNKNOWN_CITATION),
        (
            decide(world, HEALTH, reverse, rationale="there is a gap in the law"),
            Reason.UNCITED_GAP_CLAIM,
        ),
    )
    for decision, reason in cases:
        engine = engine_at(world, 60, Governance.OFF)
        engine.process(decision, expected_role=HEALTH)
        assert reason in {r for e in engine.state.log if e.kind == "rejected" for r in e.reasons}
        assert not engine.state.has_done(HEALTH, "reverse_automated_lockouts")
        assert all(not e.waived for e in engine.state.log)


def test_an_impostor_decision_is_still_rejected(world: tuple[Scenario, RoleSet]) -> None:
    engine = engine_at(world, 60, Governance.OFF)
    reverse = ProposedAction(action_type="reverse_automated_lockouts")
    engine.process(decide(world, HEALTH, reverse), expected_role=TELECOM)
    assert Reason.WRONG_ROLE_OR_TIME in {r for e in engine.state.log for r in e.reasons}
    assert not engine.state.has_done(HEALTH, "reverse_automated_lockouts")
