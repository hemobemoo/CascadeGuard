"""ScriptedAgent: decisions read from a scenario's scripted_decisions.yaml. No LLM, no API key.

This is the test baseline and the demo fallback (AGENTS.md "Determinism and replay").
"""

import copy
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, ValidationError

from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.decisions import AgentDecision, Citation, ProposedAction
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.simulation.boundaries import RoleView


class ScriptedEntry(DomainModel):
    role: str
    at_minute: int = Field(ge=0)
    actions: tuple[ProposedAction, ...] = Field(min_length=1)
    rationale: str
    citations: tuple[Citation, ...] = ()
    uncertainty: tuple[str, ...] = ()


class ScriptedDecisions(DomainModel):
    scenario: str
    decisions: tuple[ScriptedEntry, ...]


class ScriptedAgentError(ValueError):
    pass


class ScriptedAgent:
    def __init__(self, role_id: str, entries: tuple[ScriptedEntry, ...]) -> None:
        self.role_id = role_id
        self._by_minute = {e.at_minute: e for e in entries if e.role == role_id}

    def observe(self, view: RoleView) -> AgentDecision:
        entry = self._by_minute.get(view.minute)
        if entry is None:
            return AgentDecision(
                role_id=self.role_id,
                at=view.at,
                proposed_actions=(),
                rationale="No scripted decision at this step.",
                citations=(),
                uncertainty=(),
            )
        return AgentDecision(
            role_id=self.role_id,
            at=view.at,
            # Fresh copies: an agent's output must never alias data shared across runs.
            proposed_actions=copy.deepcopy(entry.actions),
            rationale=entry.rationale,
            citations=entry.citations,
            uncertainty=entry.uncertainty,
        )


def load_scripted_agents(
    path: Path, scenario: Scenario, roles: RoleSet
) -> dict[str, ScriptedAgent]:
    """One ScriptedAgent per role. Entries must name a known role and an inject minute."""
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        script = ScriptedDecisions.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ScriptedAgentError(f"{path.name}: {exc}") from exc
    if script.scenario != scenario.id:
        raise ScriptedAgentError(f"{path.name} is for {script.scenario}, not {scenario.id}")
    role_ids = {r.id for r in roles.roles}
    minutes = {e.at_minute for e in scenario.events}
    seen: set[tuple[str, int]] = set()
    for entry in script.decisions:
        if entry.role not in role_ids:
            raise ScriptedAgentError(f"unknown role {entry.role}")
        if entry.at_minute not in minutes:
            raise ScriptedAgentError(f"{entry.role}: T+{entry.at_minute} is not an inject minute")
        if (entry.role, entry.at_minute) in seen:
            raise ScriptedAgentError(f"{entry.role}: two decisions at T+{entry.at_minute}")
        seen.add((entry.role, entry.at_minute))
    return {r.id: ScriptedAgent(r.id, script.decisions) for r in roles.roles}
