"""Accept or reject proposed actions against the loaded clauses, and apply accepted effects.

This is the only code that changes simulation state in response to agents. Checks use each
clause's `normalized` reading; `stated` and `interpreted` readings are treated the same.
"""

from dataclasses import dataclass
from enum import StrEnum

from cascadeguard.domain.decisions import AgentDecision, ProposedAction
from cascadeguard.domain.findings import Finding
from cascadeguard.domain.policies import ClauseStatus, PolicyClause, RuleKind
from cascadeguard.domain.scenario import Role, TimelineEvent
from cascadeguard.simulation.state import SimulationState

SHARE = "share_incident_status"
REQUEST = "request_information"


class Reason(StrEnum):
    """Why the engine rejected an action or a decision."""

    UNKNOWN_CITATION = "unknown_citation"  # clause id not in the corpus at all
    DRAFT_CITATION = "draft_citation"  # clause exists but is not loaded (draft, not reviewed)
    WRONG_ROLE_OR_TIME = "wrong_role_or_time"
    NOT_ALLOWED_ACTION = "not_allowed_action"
    UNKNOWN_TARGET = "unknown_target"
    FACT_NOT_KNOWN = "fact_not_known"
    MISSING_PARAMETER = "missing_parameter"
    OUTSIDE_RECIPIENT_BOUNDARY = "outside_recipient_boundary"
    RESTRICTED_BY_CLAUSE = "restricted_by_clause"
    MISSING_PREREQUISITE = "missing_prerequisite"
    MISSING_INFORMATION = "missing_information"
    NO_AUTHORITY = "no_authority"
    AUTHORITY_UNCERTAIN = "authority_uncertain"


class Authority(StrEnum):
    AUTHORISED = "authorised"
    UNCERTAIN = "uncertain"  # only clauses with binding: unknown support it
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Verdict:
    accepted: bool
    reasons: tuple[Reason, ...]
    clause_ids: tuple[str, ...]  # clauses that decided it (authority or restriction)
    detail: str


class RuleBook:
    """Indexes over the loaded clauses' `normalized` readings."""

    def __init__(self, clauses: dict[str, PolicyClause]) -> None:
        self.clauses = clauses

    def _matching(self, kinds: set[RuleKind], action: str, actor: str) -> list[PolicyClause]:
        return [
            c
            for c in self.clauses.values()
            if (n := c.normalized) is not None
            and n.kind in kinds
            and n.action == action
            and n.actor in (actor, "any")
        ]

    def authority(self, role: str, action: str) -> tuple[Authority, tuple[str, ...]]:
        """Does a loaded clause make this role responsible for, or permit it, this action?

        A clause counts if it is binding, or if it is an illustrative scenario rule (binding
        false). A clause with binding: unknown only makes the authority uncertain; non-binding
        guidance (binding false, not illustrative) never counts.
        """
        candidates = self._matching({RuleKind.OBLIGATION, RuleKind.PERMISSION}, action, role)
        firm = [c.id for c in candidates if c.binding is True or _is_scenario_rule(c)]
        if firm:
            return Authority.AUTHORISED, tuple(firm)
        unsure = [c.id for c in candidates if c.binding == "unknown"]
        if unsure:
            return Authority.UNCERTAIN, tuple(unsure)
        return Authority.NONE, ()

    def restrictions(self, action: str, category: str | None, actor: str) -> tuple[str, ...]:
        """Prohibitions (and data safeguards) that forbid this action for this data category."""
        found: list[str] = []
        for c in self._matching({RuleKind.PROHIBITION, RuleKind.SAFEGUARD}, action, actor):
            n = c.normalized
            assert n is not None
            # A data rule restricts only its own category; a general prohibition always applies.
            if n.data_category is not None:
                applies = n.data_category == category
            else:
                applies = n.kind is RuleKind.PROHIBITION
            if applies:
                found.append(c.id)
        return tuple(found)

    def share_basis(self, category: str) -> tuple[str, ...]:
        """Loaded clauses that permit or oblige sharing this data category (any actor)."""
        return tuple(
            c.id
            for c in self.clauses.values()
            if (n := c.normalized) is not None
            and n.kind in (RuleKind.OBLIGATION, RuleKind.PERMISSION)
            and n.action == SHARE
            and n.data_category == category
        )

    def obligations_for(self, action: str) -> tuple[str, ...]:
        """Loaded clauses that oblige someone to take this action (a trigger)."""
        return tuple(
            c.id
            for c in self.clauses.values()
            if (n := c.normalized) is not None
            and n.kind is RuleKind.OBLIGATION
            and n.action == action
        )


def _is_scenario_rule(clause: PolicyClause) -> bool:
    return clause.status is ClauseStatus.ILLUSTRATIVE and clause.binding is False


class ConstraintEngine:
    def __init__(
        self,
        state: SimulationState,
        clauses: dict[str, PolicyClause],
        corpus_clause_ids: frozenset[str],
    ) -> None:
        self.state = state
        self.rules = RuleBook(clauses)
        self.corpus_clause_ids = corpus_clause_ids  # every clause id, any status

    # ----- timeline -----

    def release(self, event: TimelineEvent) -> None:
        """Advance to an inject: release its facts, open its obligations, mark missed deadlines."""
        state = self.state
        for ob in state.mark_missed(event.at_minute):
            state.record(
                "obligation_missed", role=ob.role, action=ob.action, clause_ids=(ob.clause_id,)
            )
        state.advance_to(event)
        for fact in event.facts:
            for role in dict.fromkeys((fact.holder, *event.recipients)):
                if state.learn(role, fact.id):
                    state.record("fact_released", role=role, detail=fact.id)
        for clause_id in event.opens_obligations:
            self._open_obligation(clause_id)
        self._check_knowledge_goals()

    def close(self, end_minute: int) -> None:
        for ob in self.state.mark_missed(end_minute + 1):
            self.state.record(
                "obligation_missed", role=ob.role, action=ob.action, clause_ids=(ob.clause_id,)
            )

    def _open_obligation(self, clause_id: str) -> None:
        state = self.state
        clause = self.rules.clauses.get(clause_id)
        if clause is None or clause.normalized is None:
            state.add_finding(
                Finding(
                    kind="trigger_not_loaded",
                    minute=state.minute,
                    clause_ids=(clause_id,),
                    detail=f"{clause_id} would open an obligation but is not loaded by the engine",
                )
            )
            return
        n = clause.normalized
        state.open_obligation(clause_id, n.actor, n.action, n.deadline_minutes)
        state.record("obligation_opened", role=n.actor, action=n.action, clause_ids=(clause_id,))
        if n.deadline_minutes is None:
            state.add_finding(
                Finding(
                    kind="deadline_undetermined",
                    minute=state.minute,
                    role=n.actor,
                    clause_ids=(clause_id,),
                    detail=(
                        f"the deadline for {n.action} cannot be determined from the loaded clauses"
                    ),
                )
            )

    # ----- decisions -----

    def process(self, decision: AgentDecision, expected_role: str) -> None:
        state = self.state
        decision = decision.model_copy(deep=True)  # the agent keeps no handle on what we log
        cited = tuple(c.clause_id for c in decision.citations)
        if not decision.proposed_actions:
            return
        state.record("decision", role=decision.role_id, detail=decision.rationale, clause_ids=cited)
        if decision.role_id != expected_role or decision.at != state.scenario.time_at(state.minute):
            state.record("rejected", role=decision.role_id, reasons=(Reason.WRONG_ROLE_OR_TIME,))
            return
        for clause_id in cited:
            if clause_id not in self.rules.clauses:
                reason = (
                    Reason.DRAFT_CITATION
                    if clause_id in self.corpus_clause_ids
                    else Reason.UNKNOWN_CITATION
                )
                state.record(
                    "rejected",
                    role=decision.role_id,
                    reasons=(reason,),
                    clause_ids=(clause_id,),
                    detail="whole decision rejected: cited clause is not loaded by the engine",
                )
                state.add_finding(
                    Finding(
                        kind=reason.value,
                        minute=state.minute,
                        role=decision.role_id,
                        clause_ids=(clause_id,),
                        detail=f"{decision.role_id} cited {clause_id}, not loaded by the engine",
                    )
                )
                return
        role = state.roles.role(decision.role_id)
        for action in decision.proposed_actions:
            verdict = self.check(role, action)
            state.record(
                "accepted" if verdict.accepted else "rejected",
                role=role.id,
                action=action.action_type,
                target=action.target,
                detail=verdict.detail,
                reasons=tuple(r.value for r in verdict.reasons),
                clause_ids=verdict.clause_ids,
            )
            if verdict.accepted:
                self._apply(role, action)

    def check(self, role: Role, action: ProposedAction) -> Verdict:
        state = self.state
        kind = action.action_type
        if kind not in role.allowed_actions:
            return Verdict(False, (Reason.NOT_ALLOWED_ACTION,), (), f"{kind} is not allowed")
        spec = state.roles.action(kind)
        reasons: list[Reason] = []
        clause_ids: list[str] = []
        details: list[str] = []
        role_ids = {r.id for r in state.roles.roles}

        if kind in (SHARE, REQUEST) and action.target not in role_ids:
            return Verdict(False, (Reason.UNKNOWN_TARGET,), (), f"unknown target {action.target}")
        if kind == SHARE:
            fact = state.fact(action.parameters.get("fact", ""))
            if fact is None or fact not in state.known_facts(role.id):
                return Verdict(False, (Reason.FACT_NOT_KNOWN,), (), "sender does not know it")
            assert action.target is not None
            details.append(f"{fact.id} ({fact.data_category}) to {action.target}")
            if fact.data_category not in state.boundary(action.target):
                reasons.append(Reason.OUTSIDE_RECIPIENT_BOUNDARY)
            restricted = self.rules.restrictions(kind, fact.data_category, role.id)
            if restricted:
                reasons.append(Reason.RESTRICTED_BY_CLAUSE)
                clause_ids.extend(restricted)
        elif kind == REQUEST and not action.parameters.get("data_category"):
            return Verdict(False, (Reason.MISSING_PARAMETER,), (), "data_category is required")
        else:
            restricted = self.rules.restrictions(kind, None, role.id)
            if restricted:
                reasons.append(Reason.RESTRICTED_BY_CLAUSE)
                clause_ids.extend(restricted)

        missing_prior = [p for p in spec.requires_prior if not state.has_done(role.id, p)]
        if missing_prior:
            reasons.append(Reason.MISSING_PREREQUISITE)
            details.append("needs " + ", ".join(missing_prior))
        missing_info = [
            c for c in spec.requires_information if not state.has_seen_category(role.id, c)
        ]
        if missing_info:
            reasons.append(Reason.MISSING_INFORMATION)
            details.append("has not seen " + ", ".join(missing_info))
        if spec.requires_authority:
            authority, supporting = self.rules.authority(role.id, kind)
            if authority is Authority.NONE:
                reasons.append(Reason.NO_AUTHORITY)
                details.append("no loaded clause gives this role authority")
            elif authority is Authority.UNCERTAIN:
                reasons.append(Reason.AUTHORITY_UNCERTAIN)
                details.append("only clauses with binding: unknown support it")
            clause_ids.extend(supporting)
        return Verdict(not reasons, tuple(reasons), tuple(clause_ids), "; ".join(details))

    def _apply(self, role: Role, action: ProposedAction) -> None:
        state = self.state
        kind = action.action_type
        if kind == SHARE and action.target is not None:
            fact_id = action.parameters["fact"]
            if state.learn(action.target, fact_id):
                state.record("fact_released", role=action.target, detail=fact_id)
        state.mark_done(role.id, kind)
        for ob in state.fulfil_obligations(role.id, kind):
            state.record(
                "obligation_fulfilled", role=ob.role, action=ob.action, clause_ids=(ob.clause_id,)
            )
        for goal in state.scenario.recovery_goals:
            if kind in goal.achieved_by and state.goal_met_at(goal.id) is None:
                state.meet_goal(goal.id)
                state.record("goal_met", role=role.id, action=kind, detail=goal.id)
        self._check_knowledge_goals()

    def _check_knowledge_goals(self) -> None:
        state = self.state
        for goal in state.scenario.recovery_goals:
            target = goal.known_by
            if target is None or state.goal_met_at(goal.id) is not None:
                continue
            if state.has_seen_category(target.role, target.data_category):
                state.meet_goal(goal.id)
                state.record("goal_met", role=target.role, detail=goal.id)
