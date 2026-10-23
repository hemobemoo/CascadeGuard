"""What an agent (scripted or LLM) may return. Agents propose; only the engine decides."""

from pydantic import AwareDatetime, Field

from cascadeguard.domain.base import DomainModel


class Citation(DomainModel):
    clause_id: str  # must be a clause the engine loaded (reviewed or illustrative)
    quote_span: str | None = None  # short excerpt, optional
    relevance: str  # why this clause supports the action


class ProposedAction(DomainModel):
    action_type: str  # from the role's allowed action set
    target: str | None = None  # role, system, or data object acted on
    # Frozen model, but a dict stays mutable: the engine copies a decision on receipt.
    parameters: dict[str, str] = Field(default_factory=dict[str, str])


class AgentDecision(DomainModel):
    role_id: str
    at: AwareDatetime  # simulation time, not wall-clock
    proposed_actions: tuple[ProposedAction, ...]
    rationale: str
    citations: tuple[Citation, ...]
    uncertainty: tuple[str, ...]
