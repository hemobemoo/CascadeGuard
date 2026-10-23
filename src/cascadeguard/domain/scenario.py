"""Incident scenario: an MSEL-inspired timeline of injects, and the roles that receive them."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from cascadeguard.domain.base import DomainModel

ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"


class Certainty(StrEnum):
    CONFIRMED = "confirmed"
    SUSPECTED = "suspected"  # e.g. an AI-generated alert: not proof of what it claims
    UNKNOWN = "unknown"


class Fact(DomainModel):
    """One piece of information. Who may see it is decided by the engine, not by the fact."""

    id: str = Field(pattern=ID_PATTERN)
    statement: str
    data_category: str = Field(pattern=ID_PATTERN)
    holder: str  # role id that holds the fact when it first appears
    certainty: Certainty


class DecisionPoint(DomainModel):
    role: str  # the one role this question is put to
    question: str


class TimelineEvent(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    at_minute: int = Field(ge=0)  # minutes after scenario start (T+00)
    title: str
    description: str
    recipients: tuple[str, ...]  # role ids notified of this inject
    facts: tuple[Fact, ...] = ()
    decision_points: tuple[DecisionPoint, ...] = ()  # each shown only to its role
    relevant_clauses: tuple[str, ...] = ()  # clause ids
    # Obligation clauses this inject triggers; the engine opens one obligation per loaded clause.
    opens_obligations: tuple[str, ...] = ()
    review_points: tuple[str, ...] = ()  # outcomes a reviewer examines


class KnowledgeTarget(DomainModel):
    role: str
    data_category: str = Field(pattern=ID_PATTERN)


class RecoveryGoal(DomainModel):
    """An outcome the incident response needs. Diagnosis explains every unmet critical goal."""

    id: str = Field(pattern=ID_PATTERN)
    description: str
    critical: bool
    achieved_by: tuple[str, ...] = ()  # any one accepted action from this list achieves the goal
    known_by: KnowledgeTarget | None = None  # or: this role has seen a fact in this category

    @model_validator(mode="after")
    def _check_one_kind(self) -> Self:
        if bool(self.achieved_by) == (self.known_by is not None):
            raise ValueError(f"goal {self.id}: give exactly one of achieved_by or known_by")
        return self


class Scenario(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    title: str
    summary: str
    synthetic: Literal[True]  # scenarios are hypothetical; no real systems or personal data
    seed: int
    start_time: AwareDatetime
    events: tuple[TimelineEvent, ...] = Field(min_length=1)
    recovery_goals: tuple[RecoveryGoal, ...] = ()

    @model_validator(mode="after")
    def _check_timeline(self) -> Self:
        minutes = [e.at_minute for e in self.events]
        if minutes != sorted(minutes):
            raise ValueError("events must be in time order")
        _require_unique("event", [e.id for e in self.events])
        _require_unique("fact", [f.id for e in self.events for f in e.facts])
        _require_unique("goal", [g.id for g in self.recovery_goals])
        return self

    def time_at(self, minute: int) -> datetime:
        """Simulation time (not wall-clock) at a minute offset from T+00."""
        return self.start_time + timedelta(minutes=minute)


class InformationBoundary(DomainModel):
    """Data categories a role may see. Facts outside these never reach the role's view."""

    visible_categories: tuple[str, ...] = Field(min_length=1)
    notes: str | None = None


class Action(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    description: str
    # Needs an authority clause (obligation or permission) naming the role or "any".
    requires_authority: bool = False
    # The acting role must have seen a fact in each of these categories.
    requires_information: tuple[str, ...] = ()
    # The acting role must already have had each of these actions accepted.
    requires_prior: tuple[str, ...] = ()
    # An obligation to one of these actions gives only uncertain authority for this one (e.g. a
    # duty to keep a fallback plan, but no clause on who may activate it: decision h2).
    uncertain_authority_from: tuple[str, ...] = ()


class Role(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str
    description: str
    boundary: InformationBoundary
    allowed_actions: tuple[str, ...] = Field(min_length=1)  # action ids
    instructions: str  # role instructions given to the agent (scripted or LLM)


class RoleSet(DomainModel):
    """Contents of a scenario's roles.yaml."""

    actions: tuple[Action, ...] = Field(min_length=1)
    roles: tuple[Role, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        _require_unique("action", [a.id for a in self.actions])
        _require_unique("role", [r.id for r in self.roles])
        known = {a.id for a in self.actions}
        for role in self.roles:
            unknown = sorted(set(role.allowed_actions) - known)
            if unknown:
                raise ValueError(f"role {role.id} allows unknown actions: {unknown}")
        for action in self.actions:
            unknown = sorted({*action.requires_prior, *action.uncertain_authority_from} - known)
            if unknown:
                raise ValueError(f"action {action.id} requires unknown actions: {unknown}")
        return self

    def known_categories(self) -> frozenset[str]:
        """Every data category any role may see: the vocabulary of the scenario."""
        return frozenset(c for r in self.roles for c in r.boundary.visible_categories)

    def role(self, role_id: str) -> Role:
        return next(r for r in self.roles if r.id == role_id)

    def action(self, action_id: str) -> Action:
        return next(a for a in self.actions if a.id == action_id)


def _require_unique(kind: str, ids: list[str]) -> None:
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate {kind} ids: {duplicates}")
