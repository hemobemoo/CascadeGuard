"""Views carry no inject text for non-recipients, and tampering with a view changes nothing."""

from pathlib import Path

from cascadeguard.agents.scripted import ScriptedAgent, load_scripted_agents
from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.engine.constraints import ConstraintEngine
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.boundaries import RoleView, view_for
from cascadeguard.simulation.loader import SCENARIOS_DIR, load_scenario
from cascadeguard.simulation.orchestrator import run
from cascadeguard.simulation.state import SimulationState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "clauses"
SCENARIO = "uae_health_access"
SCRIPT = SCENARIOS_DIR / SCENARIO / "scripted_decisions.yaml"


class Spy:
    def __init__(self, inner: ScriptedAgent) -> None:
        self.role_id = inner.role_id
        self.inner = inner
        self.views: list[RoleView] = []

    def observe(self, view: RoleView) -> AgentDecision:
        self.views.append(view)
        return self.inner.observe(view)


class Tamperer:
    """Rewrites the category of every fact it is shown, then follows its script."""

    def __init__(self, inner: ScriptedAgent) -> None:
        self.role_id = inner.role_id
        self.inner = inner

    def observe(self, view: RoleView) -> AgentDecision:
        for fact in view.facts:
            vars(fact)["data_category"] = "regulatory_reports"  # writes __dict__, past frozen
        return self.inner.observe(view)


def test_non_recipients_get_no_inject_text_decision_points_or_clauses() -> None:
    clauses = load_engine_clauses(FIXTURES)
    corpus = frozenset(c.id for c in load_clauses())
    scenario, roles = load_scenario(SCENARIO, set(corpus))
    spies = {rid: Spy(a) for rid, a in load_scripted_agents(SCRIPT, scenario, roles).items()}
    run(scenario, roles, clauses, corpus, spies, "fixtures")
    events = {e.at_minute: e for e in scenario.events}
    checked = 0
    for role_id, spy in spies.items():
        for view in spy.views:
            event = events[view.minute]
            if role_id in event.recipients:
                assert view.event_description == event.description
                continue
            checked += 1
            assert view.event_id is None
            assert view.event_description == ""
            assert view.decision_points == ()
            assert view.clauses == ()
            assert view.event_title != event.title
    assert checked > 0


def test_tampering_with_view_facts_cannot_relabel_state_or_bypass_safeguards() -> None:
    clauses = load_engine_clauses(FIXTURES)
    corpus = frozenset(c.id for c in load_clauses())
    scenario, roles = load_scenario(SCENARIO, set(corpus))
    agents = {rid: Tamperer(a) for rid, a in load_scripted_agents(SCRIPT, scenario, roles).items()}
    result = run(scenario, roles, clauses, corpus, agents, "fixtures")
    to_telecom = {
        e.detail for e in result.log if e.kind == "fact_released" and e.role == "telecom_operator"
    }
    assert "locked_account_records" not in to_telecom
    facts = {f.id: f for e in scenario.events for f in e.facts}
    assert facts["locked_account_records"].data_category == "patient_account_records"


def test_view_facts_are_copies_not_state_or_scenario_objects() -> None:
    clauses = load_engine_clauses(FIXTURES)
    corpus = frozenset(c.id for c in load_clauses())
    scenario, roles = load_scenario(SCENARIO, set(corpus))
    state = SimulationState(scenario, roles)
    engine = ConstraintEngine(state, clauses, corpus)
    engine.release(scenario.events[0])
    engine.release(scenario.events[1])
    view = view_for(state, "health_service_operator", scenario.events[1], clauses, corpus)
    assert view.facts
    state_ids = {id(f) for f in state.known_facts("health_service_operator")}
    scenario_ids = {id(f) for e in scenario.events for f in e.facts}
    assert not {id(f) for f in view.facts} & (state_ids | scenario_ids)
