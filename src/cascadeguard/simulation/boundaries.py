"""What each role may see at time t: a frozen, boundary-filtered view built from the state.

Agents receive only a `RoleView`. It holds tuples, strings and frozen models, never a reference
to the state, so an agent cannot change the simulation or see facts outside its boundary.
"""

from dataclasses import dataclass
from datetime import datetime

from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import Fact, TimelineEvent
from cascadeguard.simulation.state import SimulationState


@dataclass(frozen=True, slots=True)
class ClauseSummary:
    id: str
    title: str
    status_label: str  # e.g. "illustrative" or "reviewed (interpreted)"; shown wherever cited


@dataclass(frozen=True, slots=True)
class RoleView:
    role_id: str
    role_name: str
    instructions: str
    minute: int
    at: datetime
    event_id: str
    event_title: str
    event_description: str
    decision_points: tuple[str, ...]
    facts: tuple[Fact, ...]  # only facts inside the role's boundary that the role knows
    allowed_actions: tuple[str, ...]
    clauses: tuple[ClauseSummary, ...]  # loaded clauses relevant to this inject
    own_history: tuple[str, ...]  # "T+15 raise_security_incident" for the role's accepted actions


def view_for(
    state: SimulationState,
    role_id: str,
    event: TimelineEvent,
    clauses: dict[str, PolicyClause],
) -> RoleView:
    role = state.roles.role(role_id)
    boundary = state.boundary(role_id)
    facts = tuple(f for f in state.known_facts(role_id) if f.data_category in boundary)
    relevant = tuple(
        ClauseSummary(c.id, c.title, c.status_label)
        for cid in event.relevant_clauses
        if (c := clauses.get(cid)) is not None
    )
    return RoleView(
        role_id=role.id,
        role_name=role.name,
        instructions=role.instructions,
        minute=state.minute,
        at=state.scenario.time_at(state.minute),
        event_id=event.id,
        event_title=event.title,
        event_description=event.description,
        decision_points=event.decision_points,
        facts=facts,
        allowed_actions=role.allowed_actions,
        clauses=relevant,
        own_history=tuple(f"T+{m:02d} {a}" for m, a in state.actions_done(role_id)),
    )
