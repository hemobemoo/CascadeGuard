import shutil
from pathlib import Path

import pytest
import yaml

from cascadeguard.domain.scenario import Certainty
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.simulation.loader import SCENARIOS_DIR, ScenarioLoadError, load_scenario

SCENARIO = "uae_health_access"
INSTITUTIONAL_ROLES = {
    "health_service_operator",
    "telecom_operator",
    "telecom_regulator",
    "health_data_oversight",
    "public_access_inclusion",
    "policy_legal_adviser",
}


def all_clause_ids() -> set[str]:
    return {c.id for c in load_clauses()}


def test_scenario_loads_with_the_six_institutional_roles() -> None:
    scenario, roles = load_scenario(SCENARIO, all_clause_ids())
    assert scenario.synthetic is True
    assert {r.id for r in roles.roles} == INSTITUTIONAL_ROLES
    assert "orchestrator" not in {r.id for r in roles.roles}


def test_timeline_matches_the_concept_injects() -> None:
    scenario, _ = load_scenario(SCENARIO, all_clause_ids())
    assert [e.at_minute for e in scenario.events] == [0, 15, 30, 45, 60, 75]


def test_fraud_alert_is_suspected_not_proven() -> None:
    scenario, _ = load_scenario(SCENARIO, all_clause_ids())
    facts = {f.id: f for e in scenario.events for f in e.facts}
    assert facts["fraud_alert_credential_stuffing"].certainty is Certainty.SUSPECTED


def test_health_operator_cannot_see_network_data_at_baseline() -> None:
    _, roles = load_scenario(SCENARIO, all_clause_ids())
    health = next(r for r in roles.roles if r.id == "health_service_operator")
    assert "network_incident_status" not in health.boundary.visible_categories
    assert "network_telemetry" not in health.boundary.visible_categories


def copy_scenario(tmp_path: Path) -> Path:
    shutil.copytree(SCENARIOS_DIR / SCENARIO, tmp_path / SCENARIO)
    return tmp_path / SCENARIO


def test_unknown_clause_reference_is_rejected(tmp_path: Path) -> None:
    copy_scenario(tmp_path)
    with pytest.raises(ScenarioLoadError, match="unknown clauses"):
        load_scenario(SCENARIO, set(), tmp_path)


def test_unknown_role_reference_is_rejected(tmp_path: Path) -> None:
    directory = copy_scenario(tmp_path)
    data = yaml.safe_load((directory / "scenario.yaml").read_text("utf-8"))
    data["events"][0]["recipients"] = ["orchestrator"]
    (directory / "scenario.yaml").write_text(yaml.safe_dump(data), "utf-8")
    with pytest.raises(ScenarioLoadError, match="unknown roles"):
        load_scenario(SCENARIO, all_clause_ids(), tmp_path)


def test_role_with_undefined_action_is_rejected(tmp_path: Path) -> None:
    directory = copy_scenario(tmp_path)
    data = yaml.safe_load((directory / "roles.yaml").read_text("utf-8"))
    data["roles"][0]["allowed_actions"].append("override_safeguard")
    (directory / "roles.yaml").write_text(yaml.safe_dump(data), "utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenario(SCENARIO, all_clause_ids(), tmp_path)


def test_events_out_of_time_order_are_rejected(tmp_path: Path) -> None:
    directory = copy_scenario(tmp_path)
    data = yaml.safe_load((directory / "scenario.yaml").read_text("utf-8"))
    data["events"][0]["at_minute"] = 90
    (directory / "scenario.yaml").write_text(yaml.safe_dump(data), "utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenario(SCENARIO, all_clause_ids(), tmp_path)
