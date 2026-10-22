"""The golden summary is sensitive to decision-level rejections, not only to actions."""

from pathlib import Path
from typing import Any

import yaml

from cascadeguard.agents.base import Agent
from cascadeguard.agents.scripted import ScriptedAgent, load_scripted_agents
from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.loader import SCENARIOS_DIR, load_scenario
from cascadeguard.simulation.orchestrator import run

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "clauses"
EXPECTED = ROOT / "tests" / "fixtures" / "uae_health_access" / "expected_baseline.yaml"


class Impostor:
    """Follows the public-access script but signs as the health operator."""

    role_id = "public_access_inclusion"

    def __init__(self, honest: ScriptedAgent) -> None:
        self.honest = honest

    def observe(self, view: RoleView) -> AgentDecision:
        decision = self.honest.observe(view)
        return decision.model_copy(update={"role_id": "health_service_operator"})


def test_an_impostor_decision_changes_the_summary() -> None:
    expected: dict[str, Any] = yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))
    clauses = load_engine_clauses(FIXTURES)
    corpus = frozenset(c.id for c in load_clauses())
    scenario, roles = load_scenario("uae_health_access", set(corpus))
    scripted = load_scripted_agents(
        SCENARIOS_DIR / "uae_health_access" / "scripted_decisions.yaml", scenario, roles
    )
    agents: dict[str, Agent] = dict(scripted)
    agents["public_access_inclusion"] = Impostor(scripted["public_access_inclusion"])
    result = run(scenario, roles, clauses, corpus, agents, expected["clause_set"])
    summary = result.summary()
    assert summary != expected
    assert {"minute": 60, "role": "public_access_inclusion", "reasons": ["wrong_role_or_time"]} in (
        summary["rejected_decisions"]
    )
