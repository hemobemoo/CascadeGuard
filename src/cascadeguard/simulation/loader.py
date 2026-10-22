"""Load a scenario directory (scenario.yaml + roles.yaml) and check cross-references."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from cascadeguard.domain.scenario import RoleSet, Scenario

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"


class ScenarioLoadError(ValueError):
    pass


def load_scenario(
    scenario_id: str, known_clause_ids: set[str], scenarios_dir: Path = SCENARIOS_DIR
) -> tuple[Scenario, RoleSet]:
    """Load and validate a scenario. Every referenced role and clause id must exist."""
    directory = scenarios_dir / scenario_id
    scenario = _load_model(directory / "scenario.yaml", Scenario)
    roles = _load_model(directory / "roles.yaml", RoleSet)
    if scenario.id != scenario_id:
        raise ScenarioLoadError(f"scenario.yaml id {scenario.id!r} != directory {scenario_id!r}")

    role_ids = {r.id for r in roles.roles}
    for event in scenario.events:
        unknown_roles = sorted(({*event.recipients} | {f.holder for f in event.facts}) - role_ids)
        if unknown_roles:
            raise ScenarioLoadError(f"event {event.id}: unknown roles {unknown_roles}")
        cited = {*event.relevant_clauses, *event.opens_obligations}
        unknown_clauses = sorted(cited - known_clause_ids)
        if unknown_clauses:
            raise ScenarioLoadError(f"event {event.id}: unknown clauses {unknown_clauses}")

    action_ids = {a.id for a in roles.actions}
    for goal in scenario.recovery_goals:
        unknown_actions = sorted(set(goal.achieved_by) - action_ids)
        if unknown_actions:
            raise ScenarioLoadError(f"goal {goal.id}: unknown actions {unknown_actions}")
        if goal.known_by is not None and goal.known_by.role not in role_ids:
            raise ScenarioLoadError(f"goal {goal.id}: unknown role {goal.known_by.role}")

    boundaries = {r.id: set(r.boundary.visible_categories) for r in roles.roles}
    for event in scenario.events:
        for fact in event.facts:
            if fact.data_category not in boundaries[fact.holder]:
                raise ScenarioLoadError(
                    f"fact {fact.id}: holder {fact.holder} cannot see {fact.data_category}"
                )
    return scenario, roles


def _load_model[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return model.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ScenarioLoadError(f"{path.name}: {exc}") from exc
