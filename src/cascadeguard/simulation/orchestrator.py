"""Deterministic orchestrator (not an agent, never an LLM): advances the timeline, gives each
role its boundary-filtered view, collects proposals, and hands them to the engine.

At each inject every role decides on the same snapshot (views are built before any decision is
applied), then the engine processes the decisions in roles.yaml order. Same inputs, same run.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from pydantic_core import TzInfo

from cascadeguard.agents.base import Agent
from cascadeguard.agents.scripted import ScriptedAgent
from cascadeguard.domain.decisions import AgentDecision, Citation, GapClaim, ProposedAction
from cascadeguard.domain.findings import CoordinationFailure, Finding, LogEntry
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import ConstraintEngine
from cascadeguard.engine.diagnosis import diagnose
from cascadeguard.engine.graph import DependencyGraph, build_graph
from cascadeguard.simulation.boundaries import RoleView, view_for
from cascadeguard.simulation.state import ObligationStatus, SimulationState


@dataclass(frozen=True, slots=True)
class RunResult:
    scenario_id: str
    clause_set: str  # label of the loaded clause set, shown with every result
    loaded_clauses: tuple[tuple[str, str], ...]  # (clause id, status label)
    log: tuple[LogEntry, ...]
    obligations: tuple[ObligationStatus, ...]
    goals: tuple[tuple[str, int | None], ...]  # (goal id, minute met or None)
    findings: tuple[Finding, ...]
    failures: tuple[CoordinationFailure, ...]
    # Every failure whose cause is still present, including those behind goals met another way.
    causes: tuple[CoordinationFailure, ...]
    graph: DependencyGraph
    scripted: bool  # every role was a ScriptedAgent (they do not adapt to a repair)
    # For display only: the exact view each role received at each inject, and each role's
    # information boundary (data categories) in this run.
    views: tuple[RoleView, ...]
    boundaries: tuple[tuple[str, tuple[str, ...]], ...]

    def summary(self) -> dict[str, Any]:
        """Plain data for the golden baseline comparison and exports."""
        return {
            "scenario": self.scenario_id,
            "clause_set": self.clause_set,
            "actions": [
                {
                    "minute": e.minute,
                    "role": e.role,
                    "action": e.action,
                    **({"target": e.target} if e.target else {}),
                    "verdict": e.kind,
                    **({"reasons": list(e.reasons)} if e.reasons else {}),
                }
                for e in self.log
                if e.kind in ("accepted", "rejected") and e.action is not None
            ],
            "rejected_decisions": [
                {
                    "minute": e.minute,
                    "role": e.role,
                    "reasons": list(e.reasons),
                    **({"clauses": list(e.clause_ids)} if e.clause_ids else {}),
                }
                for e in self.log
                if e.kind == "rejected" and e.action is None
            ],
            "obligations": [
                {
                    "clause": o.clause_id,
                    "role": o.role,
                    "action": o.action,
                    "due": o.due_at,
                    "fulfilled": o.fulfilled_at,
                    "missed": o.missed,
                    "firm": o.firm,
                }
                for o in self.obligations
            ],
            "facts_released": [
                {"minute": e.minute, "role": e.role, "fact": e.detail}
                for e in self.log
                if e.kind == "fact_released"
            ],
            "goals": {g: (f"met at T+{m}" if m is not None else "unmet") for g, m in self.goals},
            "findings": [
                {
                    "minute": f.minute,
                    "role": f.role,
                    "kind": f.kind,
                    **({"clauses": list(f.clause_ids)} if f.clause_ids else {}),
                }
                for f in self.findings
            ],
            "failures": [
                {
                    "id": f.id,
                    "category": f.category.value,
                    "goals": list(f.goals),
                    "roles": list(f.roles),
                    "clauses": list(f.clause_ids),
                }
                for f in self.failures
            ],
        }


class _Unreadable:
    """Stands in for agent output that cannot be rebuilt as plain data; the engine rejects it as
    a malformed decision."""


_MODELS = (AgentDecision, ProposedAction, Citation, GapClaim)
_LEAVES = (str, int, float, bool, type(None))


def _plain(value: object) -> bool:
    """True if the value holds only the exact types an AgentDecision is made of. Exact type
    checks and plain attribute reads run no code defined by the agent."""
    kind = type(value)
    if kind in _LEAVES:
        return True
    if kind is datetime:
        tz = cast(datetime, value).tzinfo
        return tz is None or type(tz) in (timezone, TzInfo)  # TzInfo: pydantic's own class
    if kind is tuple or kind is list:
        return all(_plain(v) for v in cast(Iterable[object], value))
    if kind is dict:
        items = cast(dict[object, object], value).items()
        return all(type(k) is str and _plain(v) for k, v in items)
    if kind in _MODELS:
        fields: object = object.__getattribute__(value, "__dict__")
        if type(fields) is not dict:
            return False
        return all(_plain(v) for v in cast(dict[str, object], fields).values())
    return False


def _copy(returned: object) -> object:
    """Copy an agent's decision by rebuilding it from JSON. Every nested value is first checked
    to be of an exact plain type (`_plain`), so no object of another type is serialised and no
    agent-defined code runs here; anything else reaches the engine as _Unreadable."""
    if type(returned) is not AgentDecision or not _plain(returned):
        return _Unreadable()
    try:
        return AgentDecision.model_validate_json(returned.model_dump_json())
    except Exception:  # any failure means the output is not a plain AgentDecision
        return _Unreadable()


def run(
    scenario: Scenario,
    roles: RoleSet,
    clauses: Mapping[str, PolicyClause],
    corpus_clause_ids: frozenset[str],
    agents: Mapping[str, Agent],
    clause_set: str,
) -> RunResult:
    loaded = dict(sorted(clauses.items()))
    state = SimulationState(scenario, roles)
    engine = ConstraintEngine(state, loaded, corpus_clause_ids)
    shown: list[RoleView] = []
    for event in scenario.events:
        engine.release(event)
        views = {r.id: view_for(state, r.id, event, loaded) for r in roles.roles}
        # A separately built copy is kept for display, never the object an agent was given.
        shown += [view_for(state, r.id, event, loaded) for r in roles.roles]
        # Each decision is copied as soon as it is returned, so a later agent in the same
        # step cannot alter an earlier one before the engine processes it.
        decisions = [(r.id, _copy(agents[r.id].observe(views[r.id]))) for r in roles.roles]
        for role_id, decision in decisions:
            engine.process(decision, expected_role=role_id)
    engine.close(scenario.events[-1].at_minute)
    graph = build_graph(state, loaded)
    failures = diagnose(state, graph, engine.rules, clause_set)
    causes = diagnose(state, graph, engine.rules, clause_set, include_met=True)
    return RunResult(
        scenario_id=scenario.id,
        clause_set=clause_set,
        loaded_clauses=tuple((c.id, c.status_label) for c in loaded.values()),
        log=state.log,
        obligations=state.obligations,
        goals=tuple((g.id, state.goal_met_at(g.id)) for g in scenario.recovery_goals),
        findings=state.findings,
        failures=failures,
        causes=causes,
        graph=graph,
        scripted=all(isinstance(a, ScriptedAgent) for a in agents.values()),
        views=tuple(shown),
        boundaries=tuple((r.id, tuple(sorted(state.boundary(r.id)))) for r in roles.roles),
    )
