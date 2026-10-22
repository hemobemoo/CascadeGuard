"""Deterministic orchestrator (not an agent, never an LLM): advances the timeline, gives each
role its boundary-filtered view, collects proposals, and hands them to the engine.

At each inject every role decides on the same snapshot (views are built before any decision is
applied), then the engine processes the decisions in roles.yaml order. Same inputs, same run.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cascadeguard.agents.base import Agent
from cascadeguard.domain.findings import CoordinationFailure, Finding, LogEntry
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import ConstraintEngine
from cascadeguard.engine.diagnosis import diagnose
from cascadeguard.engine.graph import DependencyGraph, build_graph
from cascadeguard.simulation.boundaries import view_for
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
    graph: DependencyGraph

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
                }
                for o in self.obligations
            ],
            "goals": {g: ("met" if m is not None else "unmet") for g, m in self.goals},
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
    for event in scenario.events:
        engine.release(event)
        views = {r.id: view_for(state, r.id, event, loaded) for r in roles.roles}
        decisions = [(r.id, agents[r.id].observe(views[r.id])) for r in roles.roles]
        for role_id, decision in decisions:
            engine.process(decision, expected_role=role_id)
    engine.close(scenario.events[-1].at_minute)
    graph = build_graph(state, loaded)
    failures = diagnose(state, graph, engine.rules, clause_set)
    return RunResult(
        scenario_id=scenario.id,
        clause_set=clause_set,
        loaded_clauses=tuple((c.id, c.status_label) for c in loaded.values()),
        log=state.log,
        obligations=state.obligations,
        goals=tuple((g.id, state.goal_met_at(g.id)) for g in scenario.recovery_goals),
        findings=state.findings,
        failures=failures,
        graph=graph,
    )
