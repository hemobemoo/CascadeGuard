"""Replay the identical incident with a repair, and compare it with the baseline.

Identical means the same scenario (seed, timeline, facts), the same agents and the same clause
set. The only changes are the repair's own: each edit becomes a hypothetical rule (an
illustrative clause with id `repair.<edit id>`, never a source clause), an escalation trigger is
added to its event's `opens_obligations`, and a minimum data share widens the recipient's
boundary by one category. Hypothetical rules are labelled as such in every output.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from cascadeguard.agents.base import Agent
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.repairs import (
    DETERMINATION_ACTION,
    RepairEdit,
    RepairOperationType,
    RepairProposal,
)
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import SHARE
from cascadeguard.simulation.loader import check_clause_references
from cascadeguard.simulation.orchestrator import RunResult, run

REPAIR_PREFIX = "repair."
REPAIR_LABEL = "hypothetical repair rule (not a source clause)"
REPAIR_ISSUER = "CascadeGuard repair search (hypothetical)"


def repair_clause_id(edit: RepairEdit) -> str:
    return REPAIR_PREFIX + edit.edit_id


def _rule(edit: RepairEdit) -> PolicyClause:
    op = edit.operation
    if op is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
        kind, action = "permission", SHARE
        text = (
            f"{edit.role} may send {edit.counterpart} facts in the category "
            f"{edit.data_category}, and nothing more."
        )
    elif op is RepairOperationType.ASSIGN_OWNER:
        kind, action = "obligation", edit.action
        text = f"{edit.role} is responsible for {edit.action}."
    elif op is RepairOperationType.DESIGNATE_DECISION_REQUESTER:
        kind, action = "obligation", DETERMINATION_ACTION
        text = (
            f"When {edit.trigger_event} occurs, {edit.role} requests a determination from "
            f"{edit.counterpart} on {edit.action}, within {edit.deadline_minutes} minutes."
        )
    else:  # escalation trigger or fallback-channel rule
        kind, action = "obligation", edit.action
        text = (
            f"When {edit.trigger_event} occurs, {edit.role} must {edit.action} within "
            f"{edit.deadline_minutes} minutes."
        )
    return PolicyClause.model_validate(
        {
            "id": repair_clause_id(edit),
            "title": f"Repair edit: {op.value}",
            "text": f"Hypothetical repair rule, not a quotation: {text}",
            "issuer": REPAIR_ISSUER,
            "jurisdiction": "simulation only",
            "document_date": "unknown",
            "status": "illustrative",
            "binding": False,
            "notes": "Candidate repair tested by replay. Needs human and institutional approval.",
            "normalized": {
                "basis": "stated",
                "kind": kind,
                "actor": edit.role,
                "action": action,
                "counterpart": edit.counterpart,
                "data_category": edit.data_category,
                "deadline_minutes": edit.deadline_minutes,
            },
        }
    )


def apply_repair(
    scenario: Scenario,
    roles: RoleSet,
    clauses: Mapping[str, PolicyClause],
    proposal: RepairProposal,
) -> tuple[Scenario, RoleSet, dict[str, PolicyClause]]:
    """The repaired world. Inputs are frozen and left unchanged."""
    repaired = dict(clauses)
    triggers: dict[str, list[str]] = {}
    widen: dict[str, list[str]] = {}
    for edit in proposal.edits:
        rule = _rule(edit)
        if rule.id in repaired:
            raise ValueError(f"{rule.id} already loaded")
        repaired[rule.id] = rule
        if edit.trigger_event is not None:
            triggers.setdefault(edit.trigger_event, []).append(rule.id)
        if edit.operation is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
            assert edit.counterpart is not None and edit.data_category is not None
            widen.setdefault(edit.counterpart, []).append(edit.data_category)
    check_clause_references([repaired[repair_clause_id(e)] for e in proposal.edits], roles)
    unknown = set(triggers) - {e.id for e in scenario.events}
    if unknown:
        raise ValueError(f"unknown trigger events {sorted(unknown)}")
    events = tuple(
        e.model_copy(update={"opens_obligations": (*e.opens_obligations, *triggers[e.id])})
        if e.id in triggers
        else e
        for e in scenario.events
    )
    new_roles = tuple(
        r.model_copy(
            update={
                "boundary": r.boundary.model_copy(
                    update={
                        "visible_categories": tuple(
                            dict.fromkeys((*r.boundary.visible_categories, *widen[r.id]))
                        )
                    }
                )
            }
        )
        if r.id in widen
        else r
        for r in roles.roles
    )
    return (
        scenario.model_copy(update={"events": events}),
        roles.model_copy(update={"roles": new_roles}),
        repaired,
    )


def replay(
    scenario: Scenario,
    roles: RoleSet,
    clauses: Mapping[str, PolicyClause],
    corpus_clause_ids: frozenset[str],
    agents: Mapping[str, Agent],
    clause_set: str,
    proposal: RepairProposal,
) -> RunResult:
    s, r, c = apply_repair(scenario, roles, clauses, proposal)
    result = run(s, r, c, corpus_clause_ids, agents, clause_set)
    labels = tuple(
        (cid, REPAIR_LABEL if cid.startswith(REPAIR_PREFIX) else label)
        for cid, label in result.loaded_clauses
    )
    return replace(result, loaded_clauses=labels)


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    """Baseline versus replay of the identical incident with one repair."""

    proposal: RepairProposal
    baseline: RunResult
    replay: RunResult
    critical_goals: tuple[str, ...]

    @property
    def removed(self) -> tuple[str, ...]:
        """Baseline failures that no longer occur."""
        after = {f.id for f in self.replay.failures}
        return tuple(f.id for f in self.baseline.failures if f.id not in after)

    @property
    def remaining(self) -> tuple[str, ...]:
        before = {f.id for f in self.baseline.failures}
        return tuple(f.id for f in self.replay.failures if f.id in before)

    @property
    def new_conflicts(self) -> tuple[str, ...]:
        """Failures the repair introduced."""
        before = {f.id for f in self.baseline.failures}
        return tuple(f.id for f in self.replay.failures if f.id not in before)

    @property
    def critical_blockers_removed(self) -> int:
        critical = set(self.critical_goals)
        return sum(
            1 for f in self.baseline.failures if f.id in self.removed and critical & set(f.goals)
        )

    @property
    def unmet_critical_goals(self) -> tuple[str, ...]:
        met = dict(self.replay.goals)
        return tuple(g for g in self.critical_goals if met.get(g) is None)

    @property
    def outcome(self) -> str:
        if self.new_conflicts:
            return "introduces new conflict"
        if not self.unmet_critical_goals:
            return "resolved"
        return "partial" if self.removed else "no effect"

    def changed_actions(self) -> list[dict[str, Any]]:
        """Actions whose verdict differs between baseline and replay (same minute, role, action)."""

        def verdicts(result: RunResult) -> dict[tuple[int, str, str, str], str]:
            return {
                (e.minute, e.role or "", e.action, e.target or ""): e.kind
                for e in result.log
                if e.kind in ("accepted", "rejected") and e.action is not None
            }

        before, after = verdicts(self.baseline), verdicts(self.replay)
        return [
            {
                "minute": k[0],
                "role": k[1],
                "action": k[2],
                **({"target": k[3]} if k[3] else {}),
                "baseline": before.get(k, "not proposed"),
                "replay": after.get(k, "not proposed"),
            }
            for k in sorted({*before, *after})
            if before.get(k) != after.get(k)
        ]

    def summary(self) -> dict[str, Any]:
        base_goals, new_goals = dict(self.baseline.goals), dict(self.replay.goals)

        def goal(m: int | None) -> str:
            return f"met at T+{m}" if m is not None else "unmet"

        return {
            "scenario": self.baseline.scenario_id,
            "clause_set": self.baseline.clause_set,
            "repair": self.proposal.repair_id,
            "requires_authorization": self.proposal.requires_authorization,
            "edits": [e.model_dump(mode="json", exclude_none=True) for e in self.proposal.edits],
            "outcome": self.outcome,
            "goals": {
                g: {"baseline": goal(base_goals[g]), "replay": goal(new_goals[g])}
                for g in base_goals
            },
            "failures_removed": list(self.removed),
            "failures_remaining": list(self.remaining),
            "new_conflicts": list(self.new_conflicts),
            "changed_actions": self.changed_actions(),
        }
