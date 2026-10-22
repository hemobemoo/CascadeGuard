"""Engine checks: allowed actions, citations, boundaries, restrictions, authority, deadlines."""

from typing import Any

import pytest

from cascadeguard.agents.scripted import ScriptedAgent
from cascadeguard.domain.decisions import AgentDecision, Citation, ProposedAction
from cascadeguard.domain.findings import FailureCategory
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import Authority, ConstraintEngine, Reason, RuleBook
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.simulation.loader import load_scenario
from cascadeguard.simulation.orchestrator import run
from cascadeguard.simulation.state import SimulationState

HEALTH, TELECOM = "health_service_operator", "telecom_operator"


def clause(cid: str, status: str, binding: Any, **normalized: Any) -> PolicyClause:
    data: dict[str, Any] = {
        "id": cid,
        "title": cid,
        "text": "Synthetic test clause.",
        "issuer": "test",
        "jurisdiction": "synthetic",
        "document_date": "unknown",
        "status": status,
        "binding": binding,
        "notes": "test",
        "normalized": {"basis": "stated", **normalized},
    }
    if status != "illustrative":
        data |= {"source_file": "doc.pdf", "page": 1}
    return PolicyClause.model_validate(data)


@pytest.fixture(scope="module")
def scenario_and_roles() -> tuple[Scenario, RoleSet]:
    return load_scenario("uae_health_access", {c.id for c in load_clauses()})


def engine_at(
    scenario_and_roles: tuple[Scenario, RoleSet], minute: int, *clauses: PolicyClause
) -> ConstraintEngine:
    scenario, roles = scenario_and_roles
    state = SimulationState(scenario, roles)
    engine = ConstraintEngine(state, {c.id: c for c in clauses}, frozenset({"draft.only"}))
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


@pytest.mark.parametrize(
    ("status", "binding", "expected"),
    [
        ("reviewed", True, Authority.AUTHORISED),
        ("illustrative", False, Authority.AUTHORISED),  # explicit scenario rule
        ("reviewed", "unknown", Authority.UNCERTAIN),
        ("illustrative", "unknown", Authority.UNCERTAIN),
        ("reviewed", False, Authority.NONE),  # non-binding guidance never gives authority
    ],
)
def test_authority_depends_on_binding_and_status(
    status: str, binding: Any, expected: Authority
) -> None:
    rules = RuleBook(
        {
            "c": clause(
                "c",
                status,
                binding,
                kind="permission",
                actor=HEALTH,
                action="activate_fallback_channel",
            )
        }
    )
    assert rules.authority(HEALTH, "activate_fallback_channel")[0] is expected
    assert rules.authority(TELECOM, "activate_fallback_channel")[0] is Authority.NONE


def test_safeguards_and_obligations_without_permission_give_no_authority() -> None:
    rules = RuleBook(
        {
            "s": clause(
                "s",
                "reviewed",
                True,
                kind="safeguard",
                actor=HEALTH,
                action="reverse_automated_lockouts",
            )
        }
    )
    assert rules.authority(HEALTH, "reverse_automated_lockouts")[0] is Authority.NONE


def test_action_outside_the_role_set_is_rejected(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(scenario_and_roles, 0)
    role = scenario_and_roles[1].role(HEALTH)
    verdict = engine.check(role, ProposedAction(action_type="suspend_ai_traffic_model"))
    assert verdict.reasons == (Reason.NOT_ALLOWED_ACTION,)


def test_share_outside_recipient_boundary_is_rejected(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(scenario_and_roles, 30)
    role = scenario_and_roles[1].role(TELECOM)
    share = ProposedAction(
        action_type="share_incident_status",
        target=HEALTH,
        parameters={"fact": "otp_delivery_status"},
    )
    assert engine.check(role, share).reasons == (Reason.OUTSIDE_RECIPIENT_BOUNDARY,)


def test_sharing_a_fact_the_sender_does_not_know_is_rejected(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(scenario_and_roles, 30)
    role = scenario_and_roles[1].role(TELECOM)
    share = ProposedAction(
        action_type="share_incident_status", target=HEALTH, parameters={"fact": "otp_failure_spike"}
    )
    assert engine.check(role, share).reasons == (Reason.FACT_NOT_KNOWN,)


def test_data_prohibition_blocks_the_share_even_inside_the_boundary(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    rule = clause(
        "p",
        "illustrative",
        False,
        kind="prohibition",
        actor="any",
        action="share_incident_status",
        data_category="network_incident_status",
    )
    engine = engine_at(scenario_and_roles, 30, rule)
    role = scenario_and_roles[1].role(TELECOM)
    share = ProposedAction(
        action_type="share_incident_status",
        target="telecom_regulator",
        parameters={"fact": "otp_delivery_status"},
    )
    verdict = engine.check(role, share)
    assert verdict.reasons == (Reason.RESTRICTED_BY_CLAUSE,)
    assert verdict.clause_ids == ("p",)


def test_reversal_needs_review_information_and_authority(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(scenario_and_roles, 60)
    role = scenario_and_roles[1].role(HEALTH)
    verdict = engine.check(role, ProposedAction(action_type="reverse_automated_lockouts"))
    assert set(verdict.reasons) == {
        Reason.MISSING_PREREQUISITE,
        Reason.MISSING_INFORMATION,
        Reason.NO_AUTHORITY,
    }


@pytest.mark.parametrize(
    ("cite", "reason"),
    [("draft.only", Reason.DRAFT_CITATION), ("no.such.clause", Reason.UNKNOWN_CITATION)],
)
def test_unloaded_citation_rejects_the_whole_decision(
    scenario_and_roles: tuple[Scenario, RoleSet], cite: str, reason: Reason
) -> None:
    scenario = scenario_and_roles[0]
    engine = engine_at(scenario_and_roles, 0)
    engine.process(
        decision(
            scenario, TELECOM, 0, ProposedAction(action_type="investigate_network_fault"), cite=cite
        ),
        expected_role=TELECOM,
    )
    assert not engine.state.has_done(TELECOM, "investigate_network_fault")
    assert engine.state.log[-1].reasons == (reason,)
    assert engine.state.findings[-1].kind == reason.value


def test_decision_for_another_role_or_time_is_rejected(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    scenario = scenario_and_roles[0]
    engine = engine_at(scenario_and_roles, 0)
    act = ProposedAction(action_type="investigate_network_fault")
    engine.process(decision(scenario, TELECOM, 0, act), expected_role=HEALTH)
    engine.process(decision(scenario, TELECOM, 15, act), expected_role=TELECOM)
    assert [e.reasons for e in engine.state.log if e.kind == "rejected"] == [
        (Reason.WRONG_ROLE_OR_TIME,),
        (Reason.WRONG_ROLE_OR_TIME,),
    ]
    assert not engine.state.has_done(TELECOM, "investigate_network_fault")


def test_missed_deadline_is_a_temporal_infeasibility(
    scenario_and_roles: tuple[Scenario, RoleSet],
) -> None:
    scenario, roles = scenario_and_roles
    report = clause(
        "illus.telecom.incident-report",
        "illustrative",
        False,
        kind="obligation",
        actor=TELECOM,
        action="report_to_telecom_regulator",
        deadline_minutes=60,
    )
    silent = {r.id: ScriptedAgent(r.id, ()) for r in roles.roles}
    result = run(scenario, roles, {report.id: report}, frozenset({report.id}), silent, "test")
    (ob,) = result.obligations
    assert ob.missed and ob.fulfilled_at is None
    temporal = [f for f in result.failures if f.category is FailureCategory.TEMPORAL_INFEASIBILITY]
    assert [f.subject for f in temporal] == ["report_to_telecom_regulator"]
