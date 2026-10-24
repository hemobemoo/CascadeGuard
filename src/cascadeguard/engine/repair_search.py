"""Search the closed repair grammar for the smallest safe repair (AGENTS.md, CascadeGuard.md §6),
and judge each replay. Judging lives here, in the engine: `simulation/replay.py` only applies a
repair and reruns the incident.

1. Candidate edits come only from the baseline's diagnosed failures and blocked data shares.
2. Hard filter, before replay: an edit under which a restricted action (prohibition or
   safeguard, conditional or not) would become permitted is discarded with its reason. A data
   share widens the recipient's boundary whoever sends, so it is checked for every role. A repair
   never decides that a condition is met.
3. Every remaining repair of up to MAX_EDITS edits is replayed on the identical incident.
   Hard filter, after replay: the repair is discarded if the replay accepts an action the
   baseline held back under a prohibition or safeguard, or delivers to a new role a fact whose
   category a prohibition or safeguard names.
4. Ranking is lexicographic (ADR 0001): clean repairs (no new conflict) above any repair that
   introduces one; then resolved (every critical goal met) above partial, most critical goals
   met, most critical blockers removed (cause removed, not merely masked), fewest critical
   blockers only masked, fewest edits, fewest roles touched, fewest clauses cited; then fewest
   new conflicts, repairs not requiring authorization, and repair_id. Repairs with new
   conflicts are ranked lower, never discarded: they are the failed repairs CascadeGuard.md
   section 6 records.

A repair that creates a permission with no reviewed, binding, unconditional basis is marked
requires_authorization.
"""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from cascadeguard.domain.decisions import Citation
from cascadeguard.domain.findings import FailureCategory, LogEntry
from cascadeguard.domain.policies import ClauseStatus, RuleKind
from cascadeguard.domain.repairs import (
    DETERMINATION_ACTION,
    FALLBACK_ACTION,
    RepairEdit,
    RepairOperationType,
    RepairProposal,
)
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import SHARE, Authority, Reason, RuleBook
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.simulation.replay import REPAIR_PREFIX

MAX_EDITS = 2
SCRIPTED_LIMIT = "scripted_agent_limit"
# Labels shown wherever a comparison is printed (CLI, exports, UI).
MASKED_LABEL = "masked (goal met another way)"
REMOVED_LABEL = "removed (cause gone)"
REQUIRES_AUTHORIZATION_LABEL = "requires authorization (needs human and institutional approval)"
SCRIPTED_LIMIT_NOTE = (
    "scripted-agent limit: a duty the repair adds was never attempted because scripted agents do "
    "not adapt to a repair; revisit with LLM agents (Phase 5)"
)
DETERMINER_ACTION = "issue_determination"
_HELD_BACK = {Reason.RESTRICTED_BY_CLAUSE.value, Reason.AUTHORITY_UNCERTAIN.value}
_RESTRICTING = (RuleKind.PROHIBITION, RuleKind.SAFEGUARD)


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    """Baseline versus replay of the identical incident with one repair (engine judgement)."""

    proposal: RepairProposal
    baseline: RunResult
    replay: RunResult
    critical_goals: tuple[str, ...]

    @property
    def removed(self) -> tuple[str, ...]:
        """Baseline failures whose cause the repair removed: the replay's diagnosis, examining
        met goals too, no longer finds them."""
        present = {f.id for f in self.replay.causes}
        return tuple(f.id for f in self.baseline.failures if f.id not in present)

    @property
    def masked(self) -> tuple[str, ...]:
        """Baseline failures that no longer block only because their goal was met another way
        ("masked (goal met another way)"): the cause is still present, so they are not removed."""
        blocking = {f.id for f in self.replay.failures}
        present = {f.id for f in self.replay.causes}
        return tuple(
            f.id for f in self.baseline.failures if f.id in present and f.id not in blocking
        )

    @property
    def remaining(self) -> tuple[str, ...]:
        before = {f.id for f in self.baseline.failures}
        return tuple(f.id for f in self.replay.failures if f.id in before)

    @property
    def new_conflicts(self) -> tuple[str, ...]:
        """Failures the repair introduced."""
        before = {f.id for f in self.baseline.failures}
        return tuple(f.id for f in self.replay.failures if f.id not in before)

    def conflict_tags(self) -> dict[str, str]:
        """New conflicts that are only an unfulfilled duty caused by the scripted-agent limit: a
        missed obligation from a repair rule whose role never attempted the action, in a replay
        run entirely by scripted agents. Tagged for Phase 5, still counted as new conflicts."""
        if not self.replay.scripted:
            return {}
        new = set(self.new_conflicts)
        tags: dict[str, str] = {}
        for f in self.replay.failures:
            if f.id not in new or f.category is not FailureCategory.TEMPORAL_INFEASIBILITY:
                continue
            missed = [o for o in self.replay.obligations if o.missed and o.action == f.subject]
            if missed and all(
                o.clause_id.startswith(REPAIR_PREFIX)
                and not _attempts(self.replay.log, o.role, o.action)
                for o in missed
            ):
                tags[f.id] = SCRIPTED_LIMIT
        return tags

    @property
    def critical_blockers_removed(self) -> int:
        critical = set(self.critical_goals)
        gone = set(self.removed)
        return sum(1 for f in self.baseline.failures if f.id in gone and critical & set(f.goals))

    @property
    def critical_blockers_masked(self) -> int:
        critical = set(self.critical_goals)
        hidden = set(self.masked)
        return sum(1 for f in self.baseline.failures if f.id in hidden and critical & set(f.goals))

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
            "failures_masked": list(self.masked),
            "failures_remaining": list(self.remaining),
            "new_conflicts": list(self.new_conflicts),
            "new_conflict_tags": self.conflict_tags(),
            "changed_actions": self.changed_actions(),
        }


@dataclass(frozen=True, slots=True)
class Discarded:
    """A candidate removed by the hard filter, with its reason."""

    repair_id: str
    reason: str
    clause_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchResult:
    clause_set: str  # the baseline's clause-set label, shown with every result
    loaded_clauses: tuple[tuple[str, str], ...]  # the baseline's (clause id, status label)
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
            "ranking": RANKING,
            "ranked": [
                {
                    "rank": i + 1,
                    "repair": c.proposal.repair_id,
                    "edits": len(c.proposal.edits),
                    "requires_authorization": c.proposal.requires_authorization,
                    "critical_blockers_removed": c.critical_blockers_removed,
                    "blockers_masked": list(c.masked),
                    "outcome": c.outcome,
                    "unmet_critical_goals": list(c.unmet_critical_goals),
                    "new_conflicts": list(c.new_conflicts),
                    "new_conflict_tags": c.conflict_tags(),
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
    index = next((i for i, e in enumerate(events) if e.at_minute == first), None)
    assert index is not None, f"no inject at T+{first}"  # agents decide only at injects
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


def _restricted_by(edit: RepairEdit, rules: RuleBook, roles: RoleSet) -> tuple[str, ...]:
    if edit.operation is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
        # The widened boundary lets the category arrive from any role, not only the named sender.
        found = {
            c for r in roles.roles for c in rules.restrictions(SHARE, edit.data_category, r.id)
        }
        return tuple(sorted(found))
    assert edit.action is not None
    return rules.restrictions(edit.action, None, edit.role)


def share_senders(edit: RepairEdit, roles: RoleSet) -> tuple[str, ...]:
    """Every role that could send the category to the counterpart once the counterpart's boundary
    is widened: any role allowed to share that may itself see the category."""
    assert edit.data_category is not None
    return tuple(
        r.id
        for r in roles.roles
        if r.id != edit.counterpart
        and SHARE in r.allowed_actions
        and edit.data_category in r.boundary.visible_categories
    )


def _share_basis(edit: RepairEdit, rules: RuleBook, roles: RoleSet) -> bool:
    """For every possible sender, a reviewed, binding, unconditional clause already permits or
    obliges sharing this category with the counterpart."""

    def covered(sender: str) -> bool:
        return any(
            (n := c.normalized) is not None
            and c.status is ClauseStatus.REVIEWED
            and c.binding is True
            and n.kind in (RuleKind.OBLIGATION, RuleKind.PERMISSION)
            and n.action == SHARE
            and n.data_category == edit.data_category
            and n.actor in (sender, "any")
            and n.counterpart in (edit.counterpart, None)
            and not n.condition
            for c in rules.clauses.values()
        )

    return all(covered(s) for s in share_senders(edit, roles))


def _needs_authorization(edit: RepairEdit, rules: RuleBook, roles: RoleSet) -> bool:
    """True if the edit creates a permission that no reviewed, binding clause already gives."""
    op = edit.operation
    if op is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
        return not _share_basis(edit, rules, roles)
    # A requester's rule is an obligation to request_determination; like any obligation it
    # gives authority, so it needs authorization if that action requires authority.
    action = (
        DETERMINATION_ACTION
        if op is RepairOperationType.DESIGNATE_DECISION_REQUESTER
        else edit.action
    )
    assert action is not None
    spec = roles.action(action)
    if not spec.requires_authority:
        return False
    authority, supporting = rules.authority(edit.role, action, spec.uncertain_authority_from)
    reviewed = any(
        rules.clauses[c].status is ClauseStatus.REVIEWED and rules.clauses[c].binding is True
        for c in supporting
    )
    return not (authority is Authority.AUTHORISED and reviewed)


def _restricting_clauses(rules: RuleBook, ids: tuple[str, ...]) -> list[str]:
    return [
        c
        for c in ids
        if c in rules.clauses
        and (n := rules.clauses[c].normalized) is not None
        and n.kind in _RESTRICTING
    ]


def _lifted_restrictions(
    comparison: ReplayComparison, rules: RuleBook, scenario: Scenario
) -> tuple[str, ...]:
    """Restrictions the replay got around: an action the baseline held back under a prohibition
    or safeguard is accepted, or a fact whose category a prohibition or safeguard names reaches
    a role it did not reach in the baseline. Authority clauses (e.g. a binding-unknown duty) do
    not count: a repair may add authority, never lift a restriction."""

    def key(e: LogEntry) -> tuple[int, str | None, str | None, str | None, str | None]:
        return (e.minute, e.role, e.action, e.target, e.data_category)

    accepted = {key(e) for e in comparison.replay.log if e.kind == "accepted"}
    lifted = {
        c
        for e in comparison.baseline.log
        if e.kind == "rejected"
        and e.action is not None
        and _HELD_BACK & set(e.reasons)
        and key(e) in accepted
        for c in _restricting_clauses(rules, e.clause_ids)
    }
    category = {f.id: f.data_category for e in scenario.events for f in e.facts}
    restricted_categories: dict[str, list[str]] = {}
    for c in rules.clauses.values():
        n = c.normalized
        if n is not None and n.kind in _RESTRICTING and n.data_category is not None:
            restricted_categories.setdefault(n.data_category, []).append(c.id)

    def released(result: RunResult) -> set[tuple[str | None, str]]:
        return {(e.role, e.detail) for e in result.log if e.kind == "fact_released"}

    for _, fact in released(comparison.replay) - released(comparison.baseline):
        lifted.update(restricted_categories.get(category.get(fact, ""), ()))
    return tuple(sorted(lifted))


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


RANKING = (
    "hard filter; clean repairs before repairs with new conflicts; resolved before partial; "
    "most critical goals met; most critical blockers removed (masked ones do not count); fewest "
    "critical blockers only masked; fewest edits; fewest roles touched; fewest clauses cited; "
    "fewest new conflicts; not requiring authorization; repair_id"
)


def rank_key(
    c: ReplayComparison,
) -> tuple[bool, bool, int, int, int, int, int, int, int, bool, str]:
    p = c.proposal
    roles_touched = {r for e in p.edits for r in (e.role, e.counterpart) if r is not None}
    unmet = len(c.unmet_critical_goals)
    return (
        bool(c.new_conflicts),
        unmet > 0,  # resolved: every critical goal met in the replay
        unmet,  # equivalently, most critical goals met
        -c.critical_blockers_removed,
        c.critical_blockers_masked,
        len(p.edits),
        len(roles_touched),
        len(p.citations),
        len(c.new_conflicts),
        p.requires_authorization,
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
    for edit in edits:
        restricted = _restricted_by(edit, rules, roles)
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
            lifted = _lifted_restrictions(comparison, rules, scenario)
            if lifted:
                discarded.append(
                    Discarded(p.repair_id, "the replay got around a restriction", lifted)
                )
            else:
                compared.append(comparison)
    return SearchResult(
        baseline.clause_set,
        baseline.loaded_clauses,
        tuple(sorted(compared, key=rank_key)),
        tuple(discarded),
    )
