"""Locate the cross-agency coordination failure behind every unmet critical recovery goal.

Each failure is classified into one of the five categories (CascadeGuard.md section 4). An
absent provision is reported as "not found in the loaded clause set", never as a confirmed gap.
"""

from collections.abc import Iterable

from cascadeguard.domain.findings import CoordinationFailure, FailureCategory, LogEntry
from cascadeguard.engine.constraints import Authority, Reason, RuleBook
from cascadeguard.engine.graph import DependencyGraph, node
from cascadeguard.simulation.state import SimulationState


def qualification(clause_set: str, uncertain: bool = False) -> str:
    if uncertain:
        return (
            f"Uncertain in the loaded clause set ({clause_set}): only uncertain authority was "
            "found (binding unknown, conditional, or implied); it requires a determination. This "
            "is not a confirmed legal or standards gap; it needs expert review."
        )
    return (
        f"Not found in the loaded clause set ({clause_set}). An absent provision is not a "
        "confirmed legal or standards gap; it needs expert review."
    )


def _strip(prefixed: Iterable[str]) -> tuple[str, ...]:
    return tuple(p.split(":", 1)[1] for p in prefixed)


class _Collector:
    def __init__(self, clause_set: str) -> None:
        self.by_id: dict[str, CoordinationFailure] = {}
        self.clause_set = clause_set

    def add(
        self,
        category: FailureCategory,
        subject: str,
        goal: str,
        roles: Iterable[str],
        clause_ids: Iterable[str],
        evidence: Iterable[int],
        description: str,
        uncertain: bool = False,
    ) -> None:
        fid = f"{category.value}:{subject}"
        old = self.by_id.get(fid)
        goals = (*old.goals, goal) if old else (goal,)
        self.by_id[fid] = CoordinationFailure(
            id=fid,
            category=category,
            subject=subject,
            goals=tuple(dict.fromkeys(goals)),
            roles=tuple(sorted({*(old.roles if old else ()), *roles})),
            clause_ids=tuple(sorted({*(old.clause_ids if old else ()), *clause_ids})),
            evidence=tuple(sorted({*(old.evidence if old else ()), *evidence})),
            description=old.description if old else description,
            qualification=qualification(self.clause_set, uncertain),
        )


def _rejections(log: tuple[LogEntry, ...], action: str, *reasons: Reason) -> list[LogEntry]:
    wanted = {r.value for r in reasons}
    return [e for e in log if e.kind == "rejected" and e.action == action and wanted & {*e.reasons}]


def diagnose(
    state: SimulationState, graph: DependencyGraph, rules: RuleBook, clause_set: str
) -> tuple[CoordinationFailure, ...]:
    out = _Collector(clause_set)
    log = state.log

    def deadlock(role: str, category: str, goal: str) -> None:
        held_by = _strip(graph.sources(node("category", category), "holds"))
        holders = [h for h in held_by if h != role]
        if not holders or graph.has_edge(node("role", role), "holds", node("category", category)):
            return
        outside = not graph.has_edge(node("role", role), "sees", node("category", category))
        attempts = [
            e.seq
            for e in log
            if e.action == "share_incident_status" and e.target == role and e.kind == "rejected"
        ]
        needed = [
            e.seq
            for e in log
            if e.kind == "rejected" and e.role == role and Reason.MISSING_INFORMATION in e.reasons
        ]
        why = (
            f"{category} is outside {role}'s information boundary"
            if outside
            else f"no one shared {category} with {role}"
        )
        basis = rules.share_basis(category)
        found = (
            f" Clauses that bear on such a share: {', '.join(basis)}."
            if basis
            else " No clause authorising this share was found."
        )
        out.add(
            FailureCategory.INFORMATION_DEADLOCK,
            f"{category}->{role}",
            goal,
            (role, *holders),
            basis,
            (*attempts, *needed),
            f"{role} needs {category}, held by {', '.join(holders)}, but {why}.{found}",
        )

    for goal in state.scenario.recovery_goals:
        if not goal.critical or state.goal_met_at(goal.id) is not None:
            continue
        if goal.known_by is not None:
            deadlock(goal.known_by.role, goal.known_by.data_category, goal.id)
            continue
        for action in goal.achieved_by:
            spec = state.roles.action(action)
            candidates = _strip(graph.sources(node("action", action), "may"))
            for category in spec.requires_information:
                for role in candidates:
                    deadlock(role, category, goal.id)
            evidence = [
                e.seq
                for e in _rejections(log, action, Reason.NO_AUTHORITY, Reason.AUTHORITY_UNCERTAIN)
            ]
            if spec.requires_authority:
                verdicts = {
                    role: rules.authority(role, action, spec.uncertain_authority_from)
                    for role in candidates
                }
                if not any(a is Authority.AUTHORISED for a, _ in verdicts.values()):
                    unsure = sorted(
                        {c for a, cs in verdicts.values() if a is Authority.UNCERTAIN for c in cs}
                    )
                    detail = (
                        f" Only uncertain authority was found ({', '.join(unsure)}): binding "
                        "unknown, conditional, or implied; it requires a determination."
                        if unsure
                        else ""
                    )
                    out.add(
                        FailureCategory.ORPHAN_DUTY,
                        action,
                        goal.id,
                        candidates,
                        unsure,
                        evidence,
                        f"No role has clear authority to {action}.{detail}",
                        uncertain=bool(unsure),
                    )
            for prior in spec.requires_prior:
                if not rules.obligations_for(prior):
                    out.add(
                        FailureCategory.UNDEFINED_TRIGGER,
                        prior,
                        goal.id,
                        _strip(graph.sources(node("action", prior), "may")),
                        (),
                        [e.seq for e in log if e.action == prior],
                        f"No clause triggers {prior}, which {action} depends on.",
                    )

    for ob in state.obligations:
        if ob.missed:
            out.add(
                FailureCategory.TEMPORAL_INFEASIBILITY,
                ob.action,
                "obligations",
                (ob.role,),
                (ob.clause_id,),
                [e.seq for e in log if e.kind == "obligation_missed" and e.action == ob.action],
                f"{ob.role} did not complete {ob.action} by T+{ob.due_at}."
                + ("" if ob.firm else " The obligation itself is uncertain (binding: unknown)."),
                uncertain=not ob.firm,
            )
    return tuple(sorted(out.by_id.values(), key=lambda f: f.id))
