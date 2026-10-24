"""Replay the identical incident with a repair applied.

Identical means the same scenario (seed, timeline, facts), the same agents and the same clause
set. The only changes are the repair's own: each edit becomes a hypothetical rule (an
illustrative clause with id `repair.<edit id>`, never a source clause and never citable), an
escalation trigger is added to its event's `opens_obligations`, and a minimum data share widens
the recipient's boundary by one category. Hypothetical rules are labelled as such in every
output. Judging the replay (outcome, blockers, ranking) is the engine's job:
`engine/repair_search.py`.
"""

from collections.abc import Mapping
from dataclasses import replace

from cascadeguard.agents.base import Agent
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.repairs import (
    DETERMINATION_ACTION,
    RepairEdit,
    RepairOperationType,
    RepairProposal,
)
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.simulation.loader import check_clause_references
from cascadeguard.simulation.orchestrator import RunResult, run

SHARE = "share_incident_status"
DETERMINER_ACTION = "issue_determination"
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
            f"{edit.counterpart} may receive facts in the category {edit.data_category}, "
            f"from {edit.role} (the original holder) or any other role that holds them, or "
            "through an inject it receives; no other category."
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
    """The repaired world. Inputs are frozen and left unchanged.

    The proposal is re-validated from plain data, so a copied or constructed object cannot carry
    an operation outside the closed grammar."""
    proposal = RepairProposal.model_validate(proposal.model_dump(mode="python"))
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
    for edit in proposal.edits:
        if edit.operation is RepairOperationType.DESIGNATE_DECISION_REQUESTER:
            assert edit.action is not None and edit.counterpart is not None
            if edit.action not in roles.role(edit.role).allowed_actions:
                raise ValueError(f"{edit.edit_id}: {edit.role} may not {edit.action}")
            if DETERMINER_ACTION not in roles.role(edit.counterpart).allowed_actions:
                raise ValueError(f"{edit.edit_id}: {edit.counterpart} issues no determinations")
    for rule in (repaired[repair_clause_id(e)] for e in proposal.edits):
        n = rule.normalized
        assert n is not None
        if n.action not in roles.role(n.actor).allowed_actions:
            raise ValueError(f"{rule.id}: {n.actor} may not {n.action}")
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
