"""What an agent (scripted or LLM) may return. Agents propose; only the engine decides."""

from typing import Literal

from pydantic import AwareDatetime, Field

from cascadeguard.domain.base import DomainModel


class Citation(DomainModel):
    clause_id: str  # must be a clause the engine loaded (reviewed or illustrative)
    quote_span: str | None = None  # short excerpt, optional
    relevance: str  # why this clause supports the action


class ProposedAction(DomainModel):
    action_type: str  # from the role's allowed action set
    target: str | None = None  # a role id; the engine rejects any other target
    # Frozen model, but a dict stays mutable: the engine copies a decision on receipt.
    parameters: dict[str, str] = Field(default_factory=dict[str, str])


# The only qualification a gap claim may carry (AGENTS.md: an absent provision is never a
# confirmed legal gap). Fixed text, so it cannot be negated or reworded.
GAP_QUALIFICATION = "absent from the reviewed corpus; candidate finding, not a confirmed gap"


class GapClaim(DomainModel):
    """A suspected legal or standards gap. The only place an agent may state one: gap wording in
    free text (rationale, uncertainty) is rejected by the engine."""

    statement: str = Field(min_length=1)  # what was not found, e.g. "no clause assigns X"
    citations: tuple[Citation, ...] = Field(min_length=1)  # the evidence searched / nearest rules
    qualification: Literal[
        "absent from the reviewed corpus; candidate finding, not a confirmed gap"
    ]


class AgentDecision(DomainModel):
    role_id: str
    at: AwareDatetime  # simulation time, not wall-clock
    proposed_actions: tuple[ProposedAction, ...]
    rationale: str
    citations: tuple[Citation, ...]
    uncertainty: tuple[str, ...]
    gap_claims: tuple[GapClaim, ...] = ()
