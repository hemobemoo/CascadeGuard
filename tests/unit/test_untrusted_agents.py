"""Agents are untrusted: unvalidated objects, self-targets, future facts and bad citations."""

from typing import Any

import pytest

from cascadeguard.domain.decisions import AgentDecision, Citation, ProposedAction
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import WITHHELD, ConstraintEngine, Reason
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.simulation.loader import load_scenario
from cascadeguard.simulation.state import SimulationState

HEALTH, TELECOM = "health_service_operator", "telecom_operator"


@pytest.fixture(scope="module")
def world() -> tuple[Scenario, RoleSet]:
    return load_scenario("uae_health_access", {c.id for c in load_clauses()})


def engine_at(
    world: tuple[Scenario, RoleSet], minute: int, *rules: PolicyClause
) -> ConstraintEngine:
    scenario, roles = world
    engine = ConstraintEngine(
        SimulationState(scenario, roles),
        {c.id: c for c in rules},
        frozenset({"draft.only", *(c.id for c in rules)}),
    )
    for event in scenario.events:
        if event.at_minute <= minute:
            engine.release(event)
    return engine


def released_to(engine: ConstraintEngine, role: str) -> set[str]:
    return {e.detail for e in engine.state.log if e.kind == "fact_released" and e.role == role}


class TwoFaced(dict[str, str]):
    """A dict that reports one fact to .get() (the check) and holds another (the delivery)."""

    def get(self, key: str, default: Any = None) -> Any:  # type: ignore[override]
        return "otp_failure_spike" if key == "fact" else super().get(key, default)


def test_constructed_decision_cannot_deliver_an_unchecked_or_future_fact(
    world: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(world, 15)
    act = ProposedAction.model_construct(
        action_type="share_incident_status",
        target="public_access_inclusion",
        parameters=TwoFaced(fact="patients_still_locked_out"),  # a T+60 fact
    )
    forged = AgentDecision.model_construct(
        role_id=HEALTH,
        at=world[0].time_at(15),
        proposed_actions=(act,),
        rationale="x",
        citations=(),
        uncertainty=(),
    )
    engine.process(forged, expected_role=HEALTH)
    assert "patients_still_locked_out" not in released_to(engine, "public_access_inclusion")
    assert engine.state.log[-1].reasons == (Reason.FACT_NOT_KNOWN,)


def test_state_never_releases_a_fact_before_its_inject(world: tuple[Scenario, RoleSet]) -> None:
    engine = engine_at(world, 15)
    assert not engine.state.learn(HEALTH, "patients_still_locked_out")


@pytest.mark.parametrize("bogus", [None, "a string", {"role_id": HEALTH}])
def test_anything_but_an_agent_decision_is_a_malformed_decision(
    world: tuple[Scenario, RoleSet], bogus: object
) -> None:
    engine = engine_at(world, 0)
    engine.process(bogus, expected_role=HEALTH)
    assert [f.kind for f in engine.state.findings if f.role == HEALTH] == ["malformed_decision"]


def test_a_role_cannot_share_with_itself(world: tuple[Scenario, RoleSet]) -> None:
    engine = engine_at(world, 15)
    share = ProposedAction(
        action_type="share_incident_status", target=HEALTH, parameters={"fact": "otp_failure_spike"}
    )
    assert engine.check(world[1].role(HEALTH), share).reasons == (Reason.SELF_TARGET,)


def test_every_unloaded_citation_in_a_decision_is_a_finding(
    world: tuple[Scenario, RoleSet],
) -> None:
    engine = engine_at(world, 15)
    decision = AgentDecision(
        role_id=HEALTH,
        at=world[0].time_at(15),
        proposed_actions=(ProposedAction(action_type="raise_security_incident"),),
        rationale="x",
        citations=tuple(
            Citation(clause_id=c, relevance="x") for c in ("draft.only", "made.up", "draft.only")
        ),
        uncertainty=(),
    )
    engine.process(decision, expected_role=HEALTH)
    kinds = [(f.kind, f.clause_ids) for f in engine.state.findings if f.role == HEALTH]
    # An id outside the corpus is agent text, so the finding shows WITHHELD (Phase 4 round 1).
    assert kinds == [("draft_citation", ("draft.only",)), ("unknown_citation", (WITHHELD,))]
    assert not engine.state.has_done(HEALTH, "raise_security_incident")


def test_only_obligation_clauses_open_obligations(world: tuple[Scenario, RoleSet]) -> None:
    permission = PolicyClause.model_validate(
        {
            "id": "illus.telecom.incident-report",  # listed in opens_obligations at T+00
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
                "kind": "permission",
                "actor": TELECOM,
                "action": "report_to_telecom_regulator",
            },
        }
    )
    engine = engine_at(world, 0, permission)
    assert engine.state.obligations == ()
    assert [f.kind for f in engine.state.findings] == ["trigger_not_obligation"]
