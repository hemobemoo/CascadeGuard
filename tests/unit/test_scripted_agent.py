"""ScriptedAgent: reads scenario data, validates it, and never invents decisions."""

from pathlib import Path

import pytest
import yaml

from cascadeguard.agents.scripted import ScriptedAgent, ScriptedAgentError, load_scripted_agents
from cascadeguard.domain.scenario import Scenario
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.simulation.loader import SCENARIOS_DIR, load_scenario

SCENARIO = "uae_health_access"
SCRIPT = SCENARIOS_DIR / SCENARIO / "scripted_decisions.yaml"


def load(path: Path = SCRIPT) -> tuple[Scenario, dict[str, ScriptedAgent]]:
    scenario, roles = load_scenario(SCENARIO, {c.id for c in load_clauses()})
    return scenario, load_scripted_agents(path, scenario, roles)


def test_every_role_gets_an_agent() -> None:
    _, agents = load()
    assert set(agents) == {
        "health_service_operator",
        "telecom_operator",
        "telecom_regulator",
        "health_data_oversight",
        "public_access_inclusion",
        "policy_legal_adviser",
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"role": "orchestrator"}, "unknown role"),
        ({"at_minute": 7}, "not an inject minute"),
    ],
)
def test_bad_entries_are_rejected(tmp_path: Path, change: dict[str, object], message: str) -> None:
    data = yaml.safe_load(SCRIPT.read_text(encoding="utf-8"))
    data["decisions"][0].update(change)
    bad = tmp_path / "scripted_decisions.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ScriptedAgentError, match=message):
        load(bad)


def test_two_decisions_for_one_role_and_minute_are_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(SCRIPT.read_text(encoding="utf-8"))
    data["decisions"].append(data["decisions"][0])
    bad = tmp_path / "scripted_decisions.yaml"
    bad.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ScriptedAgentError, match="two decisions"):
        load(bad)
