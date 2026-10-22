"""The agent protocol: an agent sees one frozen role view and returns one AgentDecision."""

from typing import Protocol

from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.simulation.boundaries import RoleView


class Agent(Protocol):
    role_id: str

    def observe(self, view: RoleView) -> AgentDecision:
        """Propose actions for this step. Must not mutate anything outside the agent."""
        ...
