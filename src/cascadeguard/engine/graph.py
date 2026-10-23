"""Dependency graph of roles, data categories, actions, clauses and recovery goals (NetworkX).

Nodes are "<kind>:<id>" strings. Edges carry a `rel` attribute:
  role -sees-> category          (information boundary)
  role -holds-> category         (role knew a fact in it by the end of the run)
  role -may-> action             (allowed action)
  clause -authorises|obliges|restricts-> action, clause -binds-> role
  action -needs_info-> category, action -needs_prior-> action, action -achieves-> goal
  goal -needs_knowledge-> category, goal -for_role-> role
NetworkX ships no type stubs, so it stays inside this module behind typed helpers.
"""

from typing import Any, cast

import networkx as nx  # pyright: ignore[reportMissingTypeStubs]

from cascadeguard.domain.policies import PolicyClause, RuleKind
from cascadeguard.simulation.state import SimulationState

RELATIONS_FROM_KIND = {
    RuleKind.OBLIGATION: "obliges",
    RuleKind.PERMISSION: "authorises",
    RuleKind.PROHIBITION: "restricts",
    RuleKind.SAFEGUARD: "restricts",
}


def node(kind: str, ident: str) -> str:
    return f"{kind}:{ident}"


class DependencyGraph:
    def __init__(self) -> None:
        self._g: Any = nx.MultiDiGraph()

    def add(self, source: str, rel: str, target: str, **attrs: str) -> None:
        for n in (source, target):
            if not self._g.has_node(n):
                self._g.add_node(n, kind=n.split(":", 1)[0])
        self._g.add_edge(source, target, rel=rel, **attrs)

    def targets(self, source: str, rel: str) -> tuple[str, ...]:
        """Nodes reached from `source` by `rel` edges, sorted."""
        if not self._g.has_node(source):
            return ()
        edges = cast(list[tuple[str, str, str]], list(self._g.out_edges(source, data="rel")))
        return tuple(sorted({t for _, t, r in edges if r == rel}))

    def sources(self, target: str, rel: str) -> tuple[str, ...]:
        """Nodes with a `rel` edge into `target`, sorted."""
        if not self._g.has_node(target):
            return ()
        edges = cast(list[tuple[str, str, str]], list(self._g.in_edges(target, data="rel")))
        return tuple(sorted({s for s, _, r in edges if r == rel}))

    def has_edge(self, source: str, rel: str, target: str) -> bool:
        return target in self.targets(source, rel)

    def edges(self) -> tuple[tuple[str, str, str], ...]:
        """(source, rel, target) for every edge, sorted: for export and the UI."""
        raw = cast(list[tuple[str, str, str]], list(self._g.edges(data="rel")))
        return tuple(sorted((s, r, t) for s, t, r in raw))


def build_graph(state: SimulationState, clauses: dict[str, PolicyClause]) -> DependencyGraph:
    g = DependencyGraph()
    for role in state.roles.roles:
        r = node("role", role.id)
        for category in role.boundary.visible_categories:
            g.add(r, "sees", node("category", category))
        for action in role.allowed_actions:
            g.add(r, "may", node("action", action))
        for fact in state.known_facts(role.id):
            g.add(r, "holds", node("category", fact.data_category))
    for action in state.roles.actions:
        a = node("action", action.id)
        for category in action.requires_information:
            g.add(a, "needs_info", node("category", category))
        for prior in action.requires_prior:
            g.add(a, "needs_prior", node("action", prior))
    for goal in state.scenario.recovery_goals:
        gl = node("goal", goal.id)
        for action in goal.achieved_by:
            g.add(node("action", action), "achieves", gl)
        if goal.known_by is not None:
            g.add(gl, "needs_knowledge", node("category", goal.known_by.data_category))
            g.add(gl, "for_role", node("role", goal.known_by.role))
    for clause in clauses.values():
        n = clause.normalized
        if n is None:
            continue
        c = node("clause", clause.id)
        g.add(c, RELATIONS_FROM_KIND[n.kind], node("action", n.action), binding=str(clause.binding))
        if n.actor != "any":
            g.add(c, "binds", node("role", n.actor))
    return g
