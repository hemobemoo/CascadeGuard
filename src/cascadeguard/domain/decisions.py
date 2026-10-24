"""What an agent (scripted or LLM) may return. Agents propose; only the engine decides."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

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


# Why an agent produced no decision at a step (closed set: no model text is carried).
# invalid_output: the model's reply failed validation twice; request_failed: the API call failed
# twice; not_cached: offline mode and no cached decision for this exact view.
NoDecisionReason = Literal["invalid_output", "request_failed", "not_cached"]


class AgentDecision(DomainModel):
    role_id: str
    at: AwareDatetime  # simulation time, not wall-clock
    proposed_actions: tuple[ProposedAction, ...]
    rationale: str
    citations: tuple[Citation, ...]
    uncertainty: tuple[str, ...]
    gap_claims: tuple[GapClaim, ...] = ()
    # Set only by an LLM agent that could not decide; the engine records a no_decision finding.
    no_decision: NoDecisionReason | None = None
    # request_failed only: "<exception class> (HTTP <status>): <short message>", built by the
    # agent's code from the API error (never headers, keys or .env values; model id redacted).
    no_decision_detail: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _check_no_decision(self) -> Self:
        if self.no_decision is not None and (
            self.proposed_actions or self.citations or self.gap_claims
        ):
            raise ValueError("a no-decision step proposes nothing and cites nothing")
        if self.no_decision_detail is not None and self.no_decision != "request_failed":
            raise ValueError("only a failed request carries an error detail")
        return self
