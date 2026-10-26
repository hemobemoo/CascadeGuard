"""Load a scenario directory (scenario.yaml + roles.yaml) and check cross-references."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from cascadeguard.domain.policies import PolicyClause
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
    if scenario.owner_obligations:  # set only by a replay (simulation/replay.py)
        raise ScenarioLoadError("scenario.yaml may not set owner_obligations")

    role_ids = {r.id for r in roles.roles}
    for event in scenario.events:
        unknown_roles = sorted(({*event.recipients} | {f.holder for f in event.facts}) - role_ids)
        if unknown_roles:
            raise ScenarioLoadError(f"event {event.id}: unknown roles {unknown_roles}")
        stray = sorted({d.role for d in event.decision_points} - set(event.recipients))
        if stray:
            raise ScenarioLoadError(f"event {event.id}: decision points for non-recipients {stray}")
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


def check_clause_references(clauses: Iterable[PolicyClause], roles: RoleSet) -> None:
    """Normalized actors/counterparts must be roles (or "any"), actions must be in the catalogue,
    and data categories must be categories some role may see.

    A typo would otherwise grant nothing, or produce a false orphan duty, silently.
    """
    role_ids = {r.id for r in roles.roles} | {"any"}
    action_ids = {a.id for a in roles.actions}
    categories = roles.known_categories()
    for clause in clauses:
        n = clause.normalized
        if n is None:
            continue
        unknown = sorted(
            {n.actor, n.counterpart or "any"} - role_ids
            | ({n.action} - action_ids)
            | ({n.data_category} - categories if n.data_category is not None else set())
        )
        if unknown:
            raise ScenarioLoadError(
                f"{clause.id}: normalized names unknown roles/actions/categories {unknown}"
            )


def _load_model[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return model.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ScenarioLoadError(f"{path.name}: {exc}") from exc
