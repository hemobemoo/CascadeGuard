"""Inject text stays within what each recipient may know; categories are a closed vocabulary."""

from pathlib import Path
from typing import Any

import pytest

from cascadeguard.agents.scripted import ScriptedAgent, load_scripted_agents
from cascadeguard.domain.decisions import AgentDecision, ProposedAction
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import ConstraintEngine, Reason
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.loader import (
    SCENARIOS_DIR,
    ScenarioLoadError,
    check_clause_references,
    load_scenario,
)
from cascadeguard.simulation.orchestrator import run
from cascadeguard.simulation.state import SimulationState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "clauses"
SCENARIO = "uae_health_access"
HEALTH_SIDE = {"health_service_operator", "health_data_oversight", "public_access_inclusion"}
TELECOM_SIDE = {"telecom_operator", "telecom_regulator"}
# Words that only the other side's information would bring into an inject's text. Role names
# ("the health operator") are public; what the other side holds or sees is not.
HEALTH_WORDS = ("patient", "portal", "fraud", "lock", "alert", "mobile", "contact details")
TELECOM_WORDS = ("telemetry", "traffic-management", "traffic management", "network")


class Spy:
    def __init__(self, inner: ScriptedAgent) -> None:
        self.role_id = inner.role_id
        self.inner = inner
        self.views: list[RoleView] = []

    def observe(self, view: RoleView) -> AgentDecision:
        self.views.append(view)
        return self.inner.observe(view)


@pytest.fixture(scope="module")
def world() -> tuple[Scenario, RoleSet]:
    return load_scenario(SCENARIO, {c.id for c in load_clauses()})


def spied_run(world: tuple[Scenario, RoleSet]) -> dict[str, Spy]:
    scenario, roles = world
    clauses = load_engine_clauses(FIXTURES)
    corpus = frozenset(c.id for c in load_clauses())
    script = SCENARIOS_DIR / SCENARIO / "scripted_decisions.yaml"
    spies = {rid: Spy(a) for rid, a in load_scripted_agents(script, scenario, roles).items()}
    run(scenario, roles, clauses, corpus, spies, "fixtures")
    return spies


def inject_text(view: RoleView) -> str:
    return " ".join((view.event_title, view.event_description, *view.decision_points)).lower()


def test_inject_text_never_describes_the_other_organisation(
    world: tuple[Scenario, RoleSet],
) -> None:
    for role_id, spy in spied_run(world).items():
        banned = HEALTH_WORDS if role_id in TELECOM_SIDE else ()
        banned += TELECOM_WORDS if role_id in HEALTH_SIDE else ()
        for view in spy.views:
            text = inject_text(view)
            assert not [w for w in banned if w in text], (role_id, view.minute, text)


def test_each_role_sees_only_the_decision_points_put_to_it(
    world: tuple[Scenario, RoleSet],
) -> None:
    events = {e.at_minute: e for e in world[0].events}
    for role_id, spy in spied_run(world).items():
        for view in spy.views:
            own = tuple(
                d.question for d in events[view.minute].decision_points if d.role == role_id
            )
            assert view.decision_points == own


def engine_at(
    world: tuple[Scenario, RoleSet], minute: int, *rules: PolicyClause
) -> ConstraintEngine:
    scenario, roles = world
    engine = ConstraintEngine(
        SimulationState(scenario, roles), {c.id: c for c in rules}, frozenset()
    )
    for event in scenario.events:
        if event.at_minute <= minute:
            engine.release(event)
    return engine


def ban_requests_for(category: str) -> PolicyClause:
    return PolicyClause.model_validate(
        {
            "id": "probe.ban-request",
            "title": "t",
            "text": "Synthetic.",
            "issuer": "i",
            "jurisdiction": "j",
            "document_date": "unknown",
            "status": "illustrative",
            "binding": False,
            "notes": "n",
            "normalized": {
                "basis": "stated",
                "kind": "prohibition",
                "actor": "any",
                "action": "request_information",
                "data_category": category,
            },
        }
    )


@pytest.mark.parametrize(
    ("asked", "reason"),
    [
        ("patient_account_records", Reason.RESTRICTED_BY_CLAUSE),
        ("Patient_Account_Records", Reason.UNKNOWN_DATA_CATEGORY),
        ("patient_account_records ", Reason.UNKNOWN_DATA_CATEGORY),
        ("no_such_category", Reason.UNKNOWN_DATA_CATEGORY),
    ],
)
def test_a_misspelt_category_cannot_dodge_a_request_prohibition(
    world: tuple[Scenario, RoleSet], asked: str, reason: Reason
) -> None:
    engine = engine_at(world, 30, ban_requests_for("patient_account_records"))
    request = ProposedAction(
        action_type="request_information",
        target="health_service_operator",
        parameters={"data_category": asked},
    )
    verdict = engine.check(world[1].role("telecom_operator"), request)
    assert not verdict.accepted
    assert reason in verdict.reasons


def test_a_misspelt_category_in_a_clause_is_rejected(world: tuple[Scenario, RoleSet]) -> None:
    with pytest.raises(ScenarioLoadError, match="patient_acount_records"):
        check_clause_references([ban_requests_for("patient_acount_records")], world[1])


def test_an_empty_impostor_decision_is_still_a_finding(world: tuple[Scenario, RoleSet]) -> None:
    engine = engine_at(world, 60)
    empty: dict[str, Any] = {"proposed_actions": (), "citations": (), "uncertainty": ()}
    impostor = AgentDecision(
        role_id="telecom_operator", at=world[0].time_at(60), rationale="x", **empty
    )
    engine.process(impostor, expected_role="health_service_operator")
    kinds = [f.kind for f in engine.state.findings if f.kind != "trigger_not_loaded"]
    assert kinds == ["wrong_role_or_time"]
