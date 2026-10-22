"""What an agent (scripted or LLM) may return. Agents propose; only the engine decides."""

from datetime import datetime

from pydantic import Field

from cascadeguard.domain.base import DomainModel


class Citation(DomainModel):
    clause_id: str  # must exist in policies/reviewed/
    quote_span: str | None = None  # short excerpt, optional
    relevance: str  # why this clause supports the action


class ProposedAction(DomainModel):
    action_type: str  # from the role's allowed action set
    target: str | None = None  # role, system, or data object acted on
    parameters: dict[str, str] = Field(default_factory=dict)


class AgentDecision(DomainModel):
    role_id: str
    at: datetime  # simulation time, not wall-clock
    proposed_actions: list[ProposedAction]
    rationale: str
    citations: list[Citation]
    uncertainty: list[str]
