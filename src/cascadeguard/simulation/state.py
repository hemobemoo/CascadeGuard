"""Canonical simulation state and its append-only event log.

Only the deterministic engine (`engine/constraints.py`) and the orchestrator's timeline step call
the mutating methods here. Agents never receive this object: they get a frozen `RoleView` built
by `simulation/boundaries.py`. Every read accessor returns an immutable copy.
"""

from dataclasses import dataclass

from cascadeguard.domain.findings import Finding, LogEntry
from cascadeguard.domain.scenario import Fact, RoleSet, Scenario, TimelineEvent


@dataclass(frozen=True, slots=True)
class ObligationStatus:
    clause_id: str
    role: str
    action: str
    opened_at: int
    due_at: int | None  # None: the deadline cannot be determined from the loaded clauses
    fulfilled_at: int | None
    missed: bool


class SimulationState:
    def __init__(self, scenario: Scenario, roles: RoleSet) -> None:
        self.scenario = scenario
        self.roles = roles
        self._minute = 0
        self._facts: dict[str, Fact] = {f.id: f for e in scenario.events for f in e.facts}
        self._boundaries = {r.id: frozenset(r.boundary.visible_categories) for r in roles.roles}
        self._known: dict[str, set[str]] = {r.id: set() for r in roles.roles}
        self._done: dict[str, list[tuple[int, str]]] = {r.id: [] for r in roles.roles}
        self._goals_met: dict[str, int] = {}
        self._obligations: list[ObligationStatus] = []
        self._log: list[LogEntry] = []
        self._findings: list[Finding] = []

    # ----- read accessors (immutable results) -----

    @property
    def minute(self) -> int:
        return self._minute

    def boundary(self, role: str) -> frozenset[str]:
        return self._boundaries[role]

    def fact(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def known_facts(self, role: str) -> tuple[Fact, ...]:
        """Facts the role knows, inside its boundary, in scenario order."""
        known, boundary = self._known[role], self.boundary(role)
        return tuple(
            f for f in self._facts.values() if f.id in known and f.data_category in boundary
        )

    def has_seen_category(self, role: str, category: str) -> bool:
        return any(f.data_category == category for f in self.known_facts(role))

    def holders_of(self, category: str) -> tuple[str, ...]:
        """Roles that know at least one fact in this category, in role order."""
        return tuple(r.id for r in self.roles.roles if self.has_seen_category(r.id, category))

    def has_done(self, role: str, action: str) -> bool:
        return any(a == action for _, a in self._done[role])

    def actions_done(self, role: str) -> tuple[tuple[int, str], ...]:
        return tuple(self._done[role])

    def goal_met_at(self, goal_id: str) -> int | None:
        return self._goals_met.get(goal_id)

    @property
    def obligations(self) -> tuple[ObligationStatus, ...]:
        return tuple(self._obligations)

    @property
    def log(self) -> tuple[LogEntry, ...]:
        return tuple(self._log)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings)

    # ----- mutations (engine and orchestrator only) -----

    def advance_to(self, event: TimelineEvent) -> None:
        if event.at_minute < self._minute:
            raise ValueError("the timeline never moves backwards")
        self._minute = event.at_minute
        self.record("inject", detail=event.title)

    def learn(self, role: str, fact_id: str) -> bool:
        """Give a role a fact. Refused (False) if the category is outside its boundary."""
        fact = self._facts[fact_id]
        if fact.data_category not in self.boundary(role) or fact_id in self._known[role]:
            return False
        self._known[role].add(fact_id)
        return True

    def mark_done(self, role: str, action: str) -> None:
        self._done[role].append((self._minute, action))

    def meet_goal(self, goal_id: str) -> None:
        self._goals_met.setdefault(goal_id, self._minute)

    def open_obligation(self, clause_id: str, role: str, action: str, due_in: int | None) -> None:
        due = None if due_in is None else self._minute + due_in
        self._obligations.append(
            ObligationStatus(clause_id, role, action, self._minute, due, None, False)
        )

    def fulfil_obligations(self, role: str, action: str) -> tuple[ObligationStatus, ...]:
        fulfilled: list[ObligationStatus] = []
        for i, ob in enumerate(self._obligations):
            if ob.role == role and ob.action == action and ob.fulfilled_at is None:
                late = ob.due_at is not None and self._minute > ob.due_at
                self._obligations[i] = ObligationStatus(
                    ob.clause_id, ob.role, ob.action, ob.opened_at, ob.due_at, self._minute, late
                )
                fulfilled.append(self._obligations[i])
        return tuple(fulfilled)

    def mark_missed(self, until: int) -> tuple[ObligationStatus, ...]:
        """Mark open obligations whose deadline passed before `until` as missed."""
        missed: list[ObligationStatus] = []
        for i, ob in enumerate(self._obligations):
            due_passed = ob.due_at is not None and ob.due_at < until
            if ob.fulfilled_at is None and not ob.missed and due_passed:
                self._obligations[i] = ObligationStatus(
                    ob.clause_id, ob.role, ob.action, ob.opened_at, ob.due_at, None, True
                )
                missed.append(self._obligations[i])
        return tuple(missed)

    def record(
        self,
        kind: str,
        *,
        role: str | None = None,
        action: str | None = None,
        target: str | None = None,
        detail: str = "",
        reasons: tuple[str, ...] = (),
        clause_ids: tuple[str, ...] = (),
    ) -> LogEntry:
        entry = LogEntry(
            seq=len(self._log),
            minute=self._minute,
            kind=kind,
            role=role,
            action=action,
            target=target,
            detail=detail,
            reasons=reasons,
            clause_ids=clause_ids,
        )
        self._log.append(entry)
        return entry

    def add_finding(self, finding: Finding) -> None:
        self._findings.append(finding)
