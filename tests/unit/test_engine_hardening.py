"""Restrictions on every action kind, citations without actions, impostors, `any` obligations."""

from typing import Any

import pytest

from cascadeguard.domain.decisions import AgentDecision, Citation, ProposedAction
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import ConstraintEngine, Reason
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.simulation.loader import load_scenario
from cascadeguard.simulation.state import SimulationState

HEALTH, TELECOM = "health_service_operator", "telecom_operator"


def clause(cid: str, **normalized: Any) -> PolicyClause:
    return PolicyClause.model_validate(
        {
            "id": cid,
            "title": cid,
            "text": "Synthetic test clause.",
            "issuer": "test",
            "jurisdiction": "synthetic",
            "document_date": "unknown",
            "status": "illustrative",
            "binding": False,
            "notes": "test",
            "normalized": {"basis": "stated", **normalized},
        }
    )


@pytest.fixture(scope="module")
def world() -> tuple[Scenario, RoleSet]:
    return load_scenario("uae_health_access", {c.id for c in load_clauses()})


def engine_at(
    world: tuple[Scenario, RoleSet], minute: int, *rules: PolicyClause
) -> ConstraintEngine:
    scenario, roles = world
    engine = ConstraintEngine(
        SimulationState(scenario, roles), {c.id: c for c in rules}, frozenset(c.id for c in rules)
    )
    for event in scenario.events:
        if event.at_minute <= minute:
            engine.release(event)
    return engine


def decision(
    scenario: Scenario, role: str, minute: int, *actions: ProposedAction, cite: str = ""
) -> AgentDecision:
    return AgentDecision(
        role_id=role,
        at=scenario.time_at(minute),
        proposed_actions=actions,
        rationale="test",
        citations=(Citation(clause_id=cite, relevance="test"),) if cite else (),
        uncertainty=(),
    )


def decision_findings(engine: ConstraintEngine) -> list[str]:
    """Findings about decisions (the injects also record trigger_not_loaded for unloaded rules)."""
    return [f.kind for f in engine.state.findings if f.kind != "trigger_not_loaded"]


REQUEST_STATUS = ProposedAction(
    action_type="request_information",
    target=TELECOM,
    parameters={"data_category": "network_incident_status"},
)
REQUEST_IMPACT = ProposedAction(
    action_type="request_information",
    target=TELECOM,
    parameters={"data_category": "aggregate_access_impact"},
)
NO_STATUS_REQUESTS = {
    "kind": "prohibition",
    "actor": "any",
    "action": "request_information",
    "data_category": "network_incident_status",
}


@pytest.mark.parametrize(
    ("rule", "action", "role", "minute", "blocked"),
    [
        (NO_STATUS_REQUESTS, REQUEST_STATUS, HEALTH, 30, True),
        (NO_STATUS_REQUESTS, REQUEST_IMPACT, HEALTH, 30, False),
        (  # a category prohibition on an action that names no category applies
            {
                "kind": "prohibition",
                "actor": HEALTH,
                "action": "raise_security_incident",
                "data_category": "patient_account_records",
            },
            ProposedAction(action_type="raise_security_incident"),
            HEALTH,
            15,
            True,
        ),
        (  # a general prohibition applies to its action
            {"kind": "prohibition", "actor": "any", "action": "investigate_network_fault"},
            ProposedAction(action_type="investigate_network_fault"),
            TELECOM,
            0,
            True,
        ),
        (  # a safeguard with no data category is a protective duty, never a ban
            {"kind": "safeguard", "actor": HEALTH, "action": "review_automated_lockouts"},
            ProposedAction(action_type="review_automated_lockouts"),
            HEALTH,
            45,
            False,
        ),
    ],
)
def test_restrictions_apply_to_every_action_kind(
    world: tuple[Scenario, RoleSet],
    rule: dict[str, Any],
    action: ProposedAction,
    role: str,
    minute: int,
    blocked: bool,
) -> None:
    engine = engine_at(world, minute, clause("r", **rule))
    verdict = engine.check(world[1].role(role), action)
    assert (Reason.RESTRICTED_BY_CLAUSE in verdict.reasons) is blocked


def test_citations_are_checked_even_without_actions(world: tuple[Scenario, RoleSet]) -> None:
    engine = engine_at(world, 0)
    engine.process(decision(world[0], TELECOM, 0, cite="no.such.clause"), expected_role=TELECOM)
    assert decision_findings(engine) == ["unknown_citation"]


def test_impostor_is_a_finding_under_the_real_role_and_its_citations_still_count(
    world: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(world, 0)
    act = ProposedAction(action_type="investigate_network_fault")
    engine.process(decision(world[0], TELECOM, 0, act, cite="no.such.clause"), expected_role=HEALTH)
    assert {e.role for e in engine.state.log if e.kind == "rejected"} == {HEALTH}
    assert decision_findings(engine) == ["wrong_role_or_time", "unknown_citation"]
    assert not engine.state.has_done(TELECOM, "investigate_network_fault")


def test_obligation_on_any_role_is_fulfilled_by_whoever_acts(
    world: tuple[Scenario, RoleSet],
) -> None:
    report = clause(
        "illus.telecom.incident-report",
        kind="obligation",
        actor="any",
        action="report_to_telecom_regulator",
        deadline_minutes=60,
    )
    engine = engine_at(world, 0, report)
    for event in world[0].events:
        if 0 < event.at_minute <= 45:
            engine.release(event)
    engine.process(
        decision(world[0], TELECOM, 45, ProposedAction(action_type="report_to_telecom_regulator")),
        expected_role=TELECOM,
    )
    (ob,) = engine.state.obligations
    assert ob.fulfilled_at == 45 and not ob.missed
