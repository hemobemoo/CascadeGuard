"""An agent cannot see data outside its boundary, and cannot reach or change the state."""

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from cascadeguard.agents.scripted import ScriptedAgent, load_scripted_agents
from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.loader import SCENARIOS_DIR, load_scenario
from cascadeguard.simulation.orchestrator import run
from cascadeguard.simulation.state import SimulationState

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "clauses"
SCENARIO = "uae_health_access"


class SpyAgent:
    """Wraps a ScriptedAgent and keeps every view it was given."""

    def __init__(self, inner: ScriptedAgent) -> None:
        self.role_id = inner.role_id
        self.inner = inner
        self.views: list[RoleView] = []

    def observe(self, view: RoleView) -> AgentDecision:
        self.views.append(view)
        return self.inner.observe(view)


def run_with_spies() -> dict[str, SpyAgent]:
    clauses = load_engine_clauses(FIXTURES)
    corpus = frozenset(c.id for c in load_clauses()) | frozenset(clauses)
    scenario, roles = load_scenario(SCENARIO, set(corpus))
    scripted = load_scripted_agents(
        SCENARIOS_DIR / SCENARIO / "scripted_decisions.yaml", scenario, roles
    )
    spies = {rid: SpyAgent(agent) for rid, agent in scripted.items()}
    run(scenario, roles, clauses, corpus, spies, "fixtures")
    return spies


def walk(value: Any) -> list[Any]:
    """Every object reachable from a view's fields."""
    out = [value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            out += walk(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            out += walk(item)
    return out


def test_no_view_ever_contains_a_fact_outside_the_role_boundary() -> None:
    _, roles = load_scenario(SCENARIO, {c.id for c in load_clauses()})
    boundaries = {r.id: set(r.boundary.visible_categories) for r in roles.roles}
    for role_id, spy in run_with_spies().items():
        assert spy.views, role_id
        for view in spy.views:
            assert {f.data_category for f in view.facts} <= boundaries[role_id]


def test_health_operator_never_sees_network_data() -> None:
    spy = run_with_spies()["health_service_operator"]
    seen = {f.data_category for v in spy.views for f in v.facts}
    assert not seen & {"network_telemetry", "network_incident_status"}
    assert "otp_delivery_status" not in {f.id for v in spy.views for f in v.facts}


def test_telecom_operator_never_sees_patient_records() -> None:
    spy = run_with_spies()["telecom_operator"]
    assert "patient_account_records" not in {f.data_category for v in spy.views for f in v.facts}


def test_view_holds_no_state_and_no_mutable_containers() -> None:
    view = run_with_spies()["health_service_operator"].views[-1]
    for obj in walk(view):
        assert not isinstance(obj, (SimulationState, list, dict, set))


def test_view_cannot_be_modified() -> None:
    view = run_with_spies()["health_service_operator"].views[-1]
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.facts = ()  # type: ignore[misc]
