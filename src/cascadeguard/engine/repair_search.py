"""Search the closed repair grammar for the smallest safe repair (AGENTS.md, CascadeGuard.md §6).

1. Candidate edits come only from the baseline's diagnosed failures and blocked data shares.
2. Hard filter: an edit under which a restricted action (prohibition or safeguard, conditional
   or not) would become permitted is discarded with its reason. A repair never decides that a
   condition is met. After replay, any action accepted that the baseline held back under a
   restriction also discards the repair.
3. Every remaining repair of up to MAX_EDITS edits is replayed on the identical incident.
4. Ranking is lexicographic: most critical blockers removed, fewest edits, then repairs not
   requiring authorization, fewest roles and clauses touched, and repair_id.

A repair that creates a permission with no reviewed basis is marked requires_authorization.
"""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from cascadeguard.domain.decisions import Citation
from cascadeguard.domain.findings import FailureCategory, LogEntry
from cascadeguard.domain.policies import ClauseStatus, RuleKind
from cascadeguard.domain.repairs import (
    FALLBACK_ACTION,
    RepairEdit,
    RepairOperationType,
    RepairProposal,
)
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import SHARE, Authority, Reason, RuleBook
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.simulation.replay import ReplayComparison

MAX_EDITS = 2
DETERMINER_ACTION = "issue_determination"
_HELD_BACK = {Reason.RESTRICTED_BY_CLAUSE.value, Reason.AUTHORITY_UNCERTAIN.value}


@dataclass(frozen=True, slots=True)
class Discarded:
    """A candidate removed by the hard filter, with its reason."""

    repair_id: str
    reason: str
    clause_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchResult:
    ranked: tuple[ReplayComparison, ...]
    discarded: tuple[Discarded, ...]

    def comparison(self, repair_id: str) -> ReplayComparison:
        for c in self.ranked:
            if c.proposal.repair_id == repair_id:
                return c
        dropped = [d for d in self.discarded if d.repair_id == repair_id]
        if dropped:
            raise KeyError(f"{repair_id} was discarded: {dropped[0].reason}")
        raise KeyError(f"unknown repair {repair_id}")

    def summary(self) -> dict[str, Any]:
        return {
            "max_edits": MAX_EDITS,
            "ranked": [
                {
                    "rank": i + 1,
                    "repair": c.proposal.repair_id,
                    "edits": len(c.proposal.edits),
                    "requires_authorization": c.proposal.requires_authorization,
                    "critical_blockers_removed": c.critical_blockers_removed,
                    "outcome": c.outcome,
                    "unmet_critical_goals": list(c.unmet_critical_goals),
                    "new_conflicts": list(c.new_conflicts),
                }
                for i, c in enumerate(self.ranked)
            ],
            "discarded": [
                {"repair": d.repair_id, "reason": d.reason, "clauses": list(d.clause_ids)}
                for d in self.discarded
            ],
        }


def _attempts(log: tuple[LogEntry, ...], role: str, action: str) -> list[LogEntry]:
    return [
        e
        for e in log
        if e.kind in ("accepted", "rejected") and e.role == role and e.action == action
    ]


def _trigger(
    scenario: Scenario, log: tuple[LogEntry, ...], role: str, actions: tuple[str, ...]
) -> tuple[str, int] | None:
    """The event at which the role first attempted one of the actions in the baseline, and the
    minutes to the next inject (the new obligation's deadline)."""
    minutes = [e.minute for a in actions for e in _attempts(log, role, a)]
    if not minutes:
        return None
    first = min(minutes)
    events = scenario.events
    index = next(i for i, e in enumerate(events) if e.at_minute == first)
    nxt = events[index + 1].at_minute if index + 1 < len(events) else first
    return events[index].id, nxt - first


def candidate_edits(
    baseline: RunResult, scenario: Scenario, roles: RoleSet, rules: RuleBook
) -> dict[RepairEdit, tuple[str, ...]]:
    """Edits targeting each diagnosed failure, with the clauses each one bears on."""
    log = baseline.log
    out: dict[RepairEdit, tuple[str, ...]] = {}
    determiners = [r.id for r in roles.roles if DETERMINER_ACTION in r.allowed_actions]

    def add(edit: RepairEdit, clause_ids: tuple[str, ...]) -> None:
        out[edit] = tuple(sorted({*out.get(edit, ()), *clause_ids}))

    for f in baseline.failures:
        if f.category is FailureCategory.INFORMATION_DEADLOCK:
            category, role = f.subject.split("->")
            # A share edit widens the recipient's boundary, so it works the same whoever sends:
            # name the original holders of facts in this category, not every role that relayed one.
            holders = sorted(
                {
                    fact.holder
                    for event in scenario.events
                    for fact in event.facts
                    if fact.data_category == category and fact.holder != role
                }
            )
            for holder in holders:
                add(
                    RepairEdit(
                        operation=RepairOperationType.DEFINE_MINIMUM_DATA_SHARE,
                        role=holder,
                        counterpart=role,
                        data_category=category,
                    ),
                    f.clause_ids,
                )
        elif f.category is FailureCategory.ORPHAN_DUTY:
            for role in f.roles:
                at = _trigger(scenario, log, role, (f.subject,))
                if f.subject == FALLBACK_ACTION:
                    if at is not None:
                        add(
                            RepairEdit(
                                operation=RepairOperationType.ADD_FALLBACK_CHANNEL,
                                role=role,
                                action=f.subject,
                                trigger_event=at[0],
                                deadline_minutes=at[1],
                            ),
                            f.clause_ids,
                        )
                else:
                    add(
                        RepairEdit(
                            operation=RepairOperationType.ASSIGN_OWNER,
                            role=role,
                            action=f.subject,
                        ),
                        f.clause_ids,
                    )
                if f.clause_ids and at is not None:  # only uncertain authority was found
                    for determiner in (d for d in determiners if d != role):
                        add(
                            RepairEdit(
                                operation=RepairOperationType.DESIGNATE_DECISION_REQUESTER,
                                role=role,
                                action=f.subject,
                                counterpart=determiner,
                                trigger_event=at[0],
                                deadline_minutes=at[1],
                            ),
                            f.clause_ids,
                        )
        elif f.category is FailureCategory.UNDEFINED_TRIGGER:
            for role in f.roles:
                at = _trigger(scenario, log, role, (f.subject,))
                if at is not None:
                    add(
                        RepairEdit(
                            operation=RepairOperationType.ADD_ESCALATION_TRIGGER,
                            role=role,
                            action=f.subject,
                            trigger_event=at[0],
                            deadline_minutes=at[1],
                        ),
                        f.clause_ids,
                    )
    # Shares the baseline held back under a restriction: a minimum-share candidate each, so the
    # hard filter records why it cannot be proposed.
    for e in log:
        if (
            e.kind == "rejected"
            and e.action == SHARE
            and e.role is not None
            and e.target is not None
            and e.data_category is not None
            and _HELD_BACK & set(e.reasons)
            and rules.restrictions(SHARE, e.data_category, e.role)
        ):
            add(
                RepairEdit(
                    operation=RepairOperationType.DEFINE_MINIMUM_DATA_SHARE,
                    role=e.role,
                    counterpart=e.target,
                    data_category=e.data_category,
                ),
                e.clause_ids,
            )
    return dict(sorted(out.items(), key=lambda kv: kv[0].edit_id))


def _restricted_by(edit: RepairEdit, rules: RuleBook) -> tuple[str, ...]:
    if edit.operation is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
        return rules.restrictions(SHARE, edit.data_category, edit.role)
    assert edit.action is not None
    return rules.restrictions(edit.action, None, edit.role)


def _needs_authorization(edit: RepairEdit, rules: RuleBook, roles: RoleSet) -> bool:
    """True if the edit creates a permission that no reviewed clause already gives."""

    def reviewed(ids: tuple[str, ...]) -> bool:
        return any(
            rules.clauses[c].status is ClauseStatus.REVIEWED and rules.clauses[c].binding is True
            for c in ids
        )

    op = edit.operation
    if op is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
        assert edit.data_category is not None
        return not reviewed(rules.share_basis(edit.data_category))
    if op is RepairOperationType.DESIGNATE_DECISION_REQUESTER:
        return False  # a duty to ask for a determination grants no permission
    assert edit.action is not None
    spec = roles.action(edit.action)
    if not spec.requires_authority:
        return False
    authority, supporting = rules.authority(edit.role, edit.action, spec.uncertain_authority_from)
    return not (authority is Authority.AUTHORISED and reviewed(supporting))


def _released_restriction(comparison: ReplayComparison, rules: RuleBook) -> tuple[str, ...]:
    """Prohibitions or safeguards that held an action back in the baseline that the replay
    accepted. Authority clauses (e.g. a binding-unknown duty) do not count: a repair may add
    authority, never lift a restriction."""

    def key(e: LogEntry) -> tuple[int, str | None, str | None, str | None, str | None]:
        return (e.minute, e.role, e.action, e.target, e.data_category)

    accepted = {key(e) for e in comparison.replay.log if e.kind == "accepted"}
    return tuple(
        sorted(
            {
                c
                for e in comparison.baseline.log
                if e.kind == "rejected"
                and e.action is not None
                and _HELD_BACK & set(e.reasons)
                and key(e) in accepted
                for c in e.clause_ids
                if c in rules.clauses
                and (n := rules.clauses[c].normalized) is not None
                and n.kind in (RuleKind.PROHIBITION, RuleKind.SAFEGUARD)
            }
        )
    )


def proposal(
    edits: tuple[RepairEdit, ...],
    bears_on: dict[RepairEdit, tuple[str, ...]],
    rules: RuleBook,
    roles: RoleSet,
) -> RepairProposal:
    ordered = tuple(sorted(edits, key=lambda e: e.edit_id))
    cited = sorted({c for e in ordered for c in bears_on.get(e, ())})
    return RepairProposal(
        repair_id="+".join(e.edit_id for e in ordered),
        edits=ordered,
        rationale="; ".join(f"{e.operation.value} ({e.edit_id})" for e in ordered),
        citations=tuple(
            Citation(clause_id=c, relevance="cited by the diagnosed failure this repair targets")
            for c in cited
        ),
        requires_authorization=any(_needs_authorization(e, rules, roles) for e in ordered),
    )


def _rank_key(c: ReplayComparison) -> tuple[int, int, bool, int, int, str]:
    p = c.proposal
    roles_touched = {r for e in p.edits for r in (e.role, e.counterpart) if r is not None}
    return (
        -c.critical_blockers_removed,
        len(p.edits),
        p.requires_authorization,
        len(roles_touched),
        len(p.citations),
        p.repair_id,
    )


def search(
    baseline: RunResult,
    scenario: Scenario,
    roles: RoleSet,
    rules: RuleBook,
    replay: Callable[[RepairProposal], RunResult],
) -> SearchResult:
    edits = candidate_edits(baseline, scenario, roles, rules)
    discarded: list[Discarded] = []
    safe: list[RepairEdit] = []
    for edit, _ in edits.items():
        restricted = _restricted_by(edit, rules)
        if restricted:
            discarded.append(
                Discarded(
                    edit.edit_id,
                    "would permit an action a loaded clause restricts (a repair never decides "
                    "that a condition is met)",
                    restricted,
                )
            )
        else:
            safe.append(edit)
    critical = tuple(g.id for g in scenario.recovery_goals if g.critical)
    compared: list[ReplayComparison] = []
    for size in range(1, MAX_EDITS + 1):
        for combo in combinations(safe, size):
            p = proposal(combo, edits, rules, roles)
            comparison = ReplayComparison(p, baseline, replay(p), critical)
            released = _released_restriction(comparison, rules)
            if released:
                discarded.append(
                    Discarded(p.repair_id, "replay accepted an action held back by", released)
                )
            else:
                compared.append(comparison)
    return SearchResult(tuple(sorted(compared, key=_rank_key)), tuple(discarded))
