"""What each role may see at time t: a frozen, boundary-filtered view built from the state.

Agents receive only a `RoleView`. It holds tuples, strings and deep copies of frozen models, never
a reference to the state, so an agent cannot change the simulation or see facts outside its
boundary. Inject title and description go only to the inject's recipients and hold only what all
recipients may know (organisation-specific information is in facts). Each decision point goes
only to the role it names. Clause titles are public law, not scenario data, so recipients see
the inject's relevant clauses with their status labels. Everyone else sees that time advanced.
Each role also sees its own open obligations (ADR 0002 option A); only the engine opens, fulfils
or marks them overdue.
"""

from dataclasses import dataclass
from datetime import datetime

from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.repairs import REPAIR_LABEL, REPAIR_PREFIX
from cascadeguard.domain.scenario import Fact, TimelineEvent
from cascadeguard.knowledge.retrieval import RoleClause, clauses_for_role
from cascadeguard.simulation.state import SimulationState


@dataclass(frozen=True, slots=True)
class ClauseSummary:
    id: str
    title: str
    status_label: str  # e.g. "illustrative" or "reviewed (interpreted)"; shown wherever cited


@dataclass(frozen=True, slots=True)
class OpenObligation:
    """An obligation the engine opened for this role and that is not yet fulfilled."""

    id: str  # "<source>@T+<opened_at>", stable across runs
    action: str
    source: str  # the clause or repair rule that opened it
    source_label: str  # its status label; repair rules: REPAIR_LABEL
    opened_at: int
    due_at: int | None  # None: deadline undetermined from the loaded clauses
    status: str  # "open" or "overdue" (deadline passed, still unfulfilled)


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
    decision_points: tuple[str, ...]  # only the questions put to this role
    facts: tuple[Fact, ...]  # only facts inside the role's boundary that the role knows
    allowed_actions: tuple[str, ...]
    clauses: tuple[ClauseSummary, ...]  # loaded clauses relevant to this inject
    own_history: tuple[str, ...]  # "T+15 raise_security_incident" for the role's accepted actions
    # Loaded clauses that concern the role or its allowed actions (knowledge/retrieval.py), with
    # text and labels; repair rules in a replay appear marked not citable.
    role_clauses: tuple[RoleClause, ...]
    open_obligations: tuple[OpenObligation, ...] = ()  # this role's (or "any") unfulfilled ones


def open_obligations(
    state: SimulationState,
    role_id: str,
    clauses: dict[str, PolicyClause],
    corpus_ids: frozenset[str],
) -> tuple[OpenObligation, ...]:
    def label(cid: str) -> str:
        if cid.startswith(REPAIR_PREFIX) and cid not in corpus_ids:
            return REPAIR_LABEL
        clause = clauses.get(cid)
        return clause.status_label if clause is not None else "not loaded"

    return tuple(
        OpenObligation(
            id=f"{ob.clause_id}@T+{ob.opened_at:02d}",
            action=ob.action,
            source=ob.clause_id,
            source_label=label(ob.clause_id),
            opened_at=ob.opened_at,
            due_at=ob.due_at,
            status="overdue" if ob.missed else "open",
        )
        for ob in state.obligations
        if ob.role in (role_id, "any") and ob.fulfilled_at is None
    )


def view_for(
    state: SimulationState,
    role_id: str,
    event: TimelineEvent,
    clauses: dict[str, PolicyClause],
    corpus_ids: frozenset[str],
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
        decision_points=tuple(d.question for d in event.decision_points if d.role == role_id),
        facts=facts,
        allowed_actions=role.allowed_actions,
        clauses=relevant,
        own_history=tuple(f"T+{m:02d} {a}" for m, a in state.actions_done(role_id)),
        role_clauses=clauses_for_role(clauses, corpus_ids, role.id, role.allowed_actions),
        open_obligations=open_obligations(state, role.id, clauses, corpus_ids),
    )
