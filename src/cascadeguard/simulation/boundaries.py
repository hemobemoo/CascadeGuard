"""What each role may see at time t: a frozen, boundary-filtered view built from the state.

Agents receive only a `RoleView`. It holds tuples, strings and deep copies of frozen models,
never a reference to the state, so an agent cannot change the simulation or see facts outside its
boundary. Inject text (title, description, decision points, clauses) goes only to the inject's
recipients: it describes events in other organisations. Everyone else sees that time advanced.
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
    event_id: str | None  # None when the role is not a recipient of the inject
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
    facts = tuple(
        f.model_copy(deep=True) for f in state.known_facts(role_id) if f.data_category in boundary
    )
    recipient = role_id in event.recipients
    relevant = tuple(
        ClauseSummary(c.id, c.title, c.status_label)
        for cid in (event.relevant_clauses if recipient else ())
        if (c := clauses.get(cid)) is not None
    )
    return RoleView(
        role_id=role.id,
        role_name=role.name,
        instructions=role.instructions,
        minute=state.minute,
        at=state.scenario.time_at(state.minute),
        event_id=event.id if recipient else None,
        event_title=event.title if recipient else f"T+{state.minute:02d}: no new inject for you",
        event_description=event.description if recipient else "",
        decision_points=event.decision_points if recipient else (),
        facts=facts,
        allowed_actions=role.allowed_actions,
        clauses=relevant,
        own_history=tuple(f"T+{m:02d} {a}" for m, a in state.actions_done(role_id)),
    )
