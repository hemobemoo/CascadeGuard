"""Incident scenario: an MSEL-inspired timeline of injects, and the roles that receive them."""

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

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


class TimelineEvent(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    at_minute: int = Field(ge=0)  # minutes after scenario start (T+00)
    title: str
    description: str
    recipients: list[str]  # role ids notified of this inject
    facts: list[Fact] = Field(default_factory=list[Fact])
    decision_points: list[str] = Field(default_factory=list[str])
    relevant_clauses: list[str] = Field(default_factory=list[str])  # clause ids
    review_points: list[str] = Field(default_factory=list[str])  # outcomes a reviewer examines


class Scenario(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    title: str
    summary: str
    synthetic: Literal[True]  # scenarios are hypothetical; no real systems or personal data
    seed: int
    start_time: datetime
    events: list[TimelineEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_timeline(self) -> Self:
        minutes = [e.at_minute for e in self.events]
        if minutes != sorted(minutes):
            raise ValueError("events must be in time order")
        _require_unique("event", [e.id for e in self.events])
        _require_unique("fact", [f.id for e in self.events for f in e.facts])
        return self


class InformationBoundary(DomainModel):
    """Data categories a role may see. Facts outside these never reach the role's view."""

    visible_categories: list[str] = Field(min_length=1)
    notes: str | None = None


class Action(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    description: str


class Role(DomainModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str
    description: str
    boundary: InformationBoundary
    allowed_actions: list[str] = Field(min_length=1)  # action ids
    instructions: str  # role instructions given to the agent (scripted or LLM)


class RoleSet(DomainModel):
    """Contents of a scenario's roles.yaml."""

    actions: list[Action] = Field(min_length=1)
    roles: list[Role] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        _require_unique("action", [a.id for a in self.actions])
        _require_unique("role", [r.id for r in self.roles])
        known = {a.id for a in self.actions}
        for role in self.roles:
            unknown = sorted(set(role.allowed_actions) - known)
            if unknown:
                raise ValueError(f"role {role.id} allows unknown actions: {unknown}")
        return self


def _require_unique(kind: str, ids: list[str]) -> None:
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate {kind} ids: {duplicates}")
