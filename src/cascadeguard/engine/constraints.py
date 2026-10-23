"""Accept or reject proposed actions against the loaded clauses, and apply accepted effects.

This is the only code that changes simulation state in response to agents. Checks use each
clause's `normalized` reading; `stated` and `interpreted` readings are treated the same.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from cascadeguard.domain.decisions import AgentDecision, ProposedAction
from cascadeguard.domain.findings import Finding
from cascadeguard.domain.policies import ClauseStatus, PolicyClause, RuleKind
from cascadeguard.domain.scenario import Role, TimelineEvent
from cascadeguard.simulation.state import SimulationState

SHARE = "share_incident_status"
REQUEST = "request_information"
ANALYSIS = "provide_policy_analysis"  # may cite any loaded clause: analysing provisions is its job
# Text declaring a legal or standards gap; such a claim needs citations (AGENTS.md, 7r).
GAP_CLAIM = re.compile(
    r"\b(?:legal|regulatory|policy|standards?) gap\b|\bno (?:legal )?provision\b"
    r"|\bgap in the law\b|\bnot regulated\b|\bno law\b",
    re.IGNORECASE,
)
REQUIRES_DETERMINATION = (
    "authority uncertain - requires determination (the clause depends on a condition the engine "
    "cannot evaluate; it never decides the condition is met)"
)


class Reason(StrEnum):
    """Why the engine rejected an action or a decision."""

    MALFORMED_DECISION = "malformed_decision"  # not a valid AgentDecision
    UNKNOWN_CITATION = "unknown_citation"  # clause id not in the corpus at all
    DRAFT_CITATION = "draft_citation"  # clause exists but is not loaded (draft, not reviewed)
    CITATION_OUT_OF_SCOPE = "citation_out_of_scope"  # cited clause concerns neither role nor action
    UNCITED_GAP_CLAIM = "uncited_gap_claim"  # declares a legal gap without any citation
    WRONG_ROLE_OR_TIME = "wrong_role_or_time"
    NOT_ALLOWED_ACTION = "not_allowed_action"
    UNKNOWN_TARGET = "unknown_target"
    SELF_TARGET = "self_target"
    FACT_NOT_KNOWN = "fact_not_known"
    MISSING_PARAMETER = "missing_parameter"
    UNKNOWN_DATA_CATEGORY = "unknown_data_category"
    OUTSIDE_RECIPIENT_BOUNDARY = "outside_recipient_boundary"
    RESTRICTED_BY_CLAUSE = "restricted_by_clause"
    MISSING_PREREQUISITE = "missing_prerequisite"
    MISSING_INFORMATION = "missing_information"
    NO_AUTHORITY = "no_authority"
    AUTHORITY_UNCERTAIN = "authority_uncertain"


class Authority(StrEnum):
    AUTHORISED = "authorised"
    UNCERTAIN = "uncertain"  # binding unknown, conditional, or only implied: requires determination
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Verdict:
    accepted: bool
    reasons: tuple[Reason, ...]
    clause_ids: tuple[str, ...]  # clauses that decided it (authority or restriction)
    detail: str
    fact_id: str | None = None  # the fact a share delivers: read once, checked, then applied


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

    def authority(
        self, role: str, action: str, implied_by: tuple[str, ...] = ()
    ) -> tuple[Authority, tuple[str, ...]]:
        """Does a loaded clause make this role responsible for, or permit it, this action?

        - Firm: an obligation, or an unconditional permission, that is binding or an
          illustrative scenario rule (binding false).
        - Uncertain (requires determination): a clause with binding: unknown; a permission whose
          `condition` the engine cannot evaluate (decision 7v); or no direct clause but a firm or
          binding-unknown obligation to one of `implied_by` (e.g. a duty to keep a fallback plan
          implies only uncertain authority to activate it, decision h2).
        - Non-binding guidance (binding false, not illustrative) never counts.
        """
        candidates = self._matching({RuleKind.OBLIGATION, RuleKind.PERMISSION}, action, role)
        firm = [c.id for c in candidates if _counts(c) and not _conditional_permission(c)]
        if firm:
            return Authority.AUTHORISED, tuple(firm)
        unsure = [
            c.id
            for c in candidates
            if c.binding == "unknown" or (_counts(c) and _conditional_permission(c))
        ]
        if unsure:
            return Authority.UNCERTAIN, tuple(unsure)
        implied = [
            c.id
            for prior in implied_by
            for c in self._matching({RuleKind.OBLIGATION}, prior, role)
            if _counts(c) or c.binding == "unknown"
        ]
        if implied:
            return Authority.UNCERTAIN, tuple(dict.fromkeys(implied))
        return Authority.NONE, ()

    def is_conditional(self, clause_id: str) -> bool:
        """A prohibition, safeguard or permission whose condition the engine cannot evaluate."""
        n = self.clauses[clause_id].normalized
        return n is not None and n.kind is not RuleKind.OBLIGATION and bool(n.condition)

    def concerns(self, clause_id: str, role: str, actions: tuple[str, ...]) -> bool:
        """Does a cited clause concern the citing role or one of its actions? (decision 7n)"""
        if ANALYSIS in actions:
            return True
        n = self.clauses[clause_id].normalized
        if n is None:
            return False
        return n.actor in (role, "any") or n.counterpart == role or n.action in actions

    def restrictions(self, action: str, category: str | None, actor: str) -> tuple[str, ...]:
        """Clauses that forbid this action, for the data category it touches (if any).

        - A prohibition applies to its action. If it names a data category, it applies when the
          action touches that category, or when the action names no category (conservative).
        - A safeguard with a data category restricts the action for that category only.
        - A safeguard without a data category is a protective duty (e.g. human oversight), not a
          ban: it never blocks an action. Diagnosis uses it as context.
        """
        found: list[str] = []
        for c in self._matching({RuleKind.PROHIBITION, RuleKind.SAFEGUARD}, action, actor):
            n = c.normalized
            assert n is not None
            if n.kind is RuleKind.PROHIBITION:
                applies = n.data_category is None or category in (None, n.data_category)
            else:
                applies = n.data_category is not None and n.data_category == category
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
        """Firm obligations (binding, or illustrative scenario rules) to take this action.

        Non-binding guidance and binding: unknown clauses are not triggers.
        """
        return tuple(
            c.id
            for c in self.clauses.values()
            if (n := c.normalized) is not None
            and n.kind is RuleKind.OBLIGATION
            and n.action == action
            and (c.binding is True or _is_scenario_rule(c))
        )


def _is_scenario_rule(clause: PolicyClause) -> bool:
    return clause.status is ClauseStatus.ILLUSTRATIVE and clause.binding is False


def _counts(clause: PolicyClause) -> bool:
    """Binding, or an illustrative scenario rule: may give firm authority or a trigger."""
    return clause.binding is True or _is_scenario_rule(clause)


def _conditional_permission(clause: PolicyClause) -> bool:
    n = clause.normalized
    return n is not None and n.kind is RuleKind.PERMISSION and bool(n.condition)


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
        if clause is not None and (
            clause.normalized is None or clause.normalized.kind is not RuleKind.OBLIGATION
        ):
            state.add_finding(
                Finding(
                    kind="trigger_not_obligation",
                    minute=state.minute,
                    clause_ids=(clause_id,),
                    detail=f"{clause_id} is listed in opens_obligations but is not an obligation",
                )
            )
            return
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
        # Same firmness rule as authority: binding: unknown opens an uncertain obligation.
        firm = clause.binding is True or _is_scenario_rule(clause)
        state.open_obligation(clause_id, n.actor, n.action, n.deadline_minutes, firm=firm)
        state.record(
            "obligation_opened",
            role=n.actor,
            action=n.action,
            clause_ids=(clause_id,),
            detail="" if firm else "uncertain: binding unknown",
        )
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

    def process(self, decision: object, expected_role: str) -> None:
        """Check one agent decision. Agents are untrusted: what they return is re-validated from
        plain data, so constructed objects or subclassed containers never reach the checks.
        """
        state = self.state
        try:
            if type(decision) is not AgentDecision:
                raise TypeError(f"expected AgentDecision, got {type(decision).__name__}")
            decision = AgentDecision.model_validate(decision.model_dump(mode="python"))
        except (TypeError, ValueError) as exc:  # ValueError covers ValidationError
            state.record("rejected", role=expected_role, reasons=(Reason.MALFORMED_DECISION,))
            state.add_finding(
                Finding(
                    kind=Reason.MALFORMED_DECISION.value,
                    minute=state.minute,
                    role=expected_role,
                    detail=str(exc).splitlines()[0],
                )
            )
            return
        cited = tuple(c.clause_id for c in decision.citations)
        impostor = decision.role_id != expected_role or decision.at != state.scenario.time_at(
            state.minute
        )
        if not decision.proposed_actions and not cited and not impostor:
            return
        # Logged under the role the orchestrator asked, never the role the decision claims.
        state.record("decision", role=expected_role, detail=decision.rationale, clause_ids=cited)
        if decision.role_id != expected_role or decision.at != state.scenario.time_at(state.minute):
            claimed = f"claims role {decision.role_id} at {decision.at.isoformat()}"
            state.record(
                "rejected", role=expected_role, reasons=(Reason.WRONG_ROLE_OR_TIME,), detail=claimed
            )
            state.add_finding(
                Finding(
                    kind=Reason.WRONG_ROLE_OR_TIME.value,
                    minute=state.minute,
                    role=expected_role,
                    detail=f"decision from {expected_role} {claimed}",
                )
            )
            # Citations are still checked and recorded below; no action is taken either way.
        bad_citations = [cid for cid in dict.fromkeys(cited) if cid not in self.rules.clauses]
        for clause_id in bad_citations:  # every bad citation is its own finding
            reason = (
                Reason.DRAFT_CITATION
                if clause_id in self.corpus_clause_ids
                else Reason.UNKNOWN_CITATION
            )
            state.record(
                "rejected",
                role=expected_role,
                reasons=(reason,),
                clause_ids=(clause_id,),
                detail="whole decision rejected: cited clause is not loaded by the engine",
            )
            state.add_finding(
                Finding(
                    kind=reason.value,
                    minute=state.minute,
                    role=expected_role,
                    clause_ids=(clause_id,),
                    detail=f"{expected_role} cited {clause_id}, not loaded by the engine",
                )
            )
        if bad_citations:
            return
        actions = tuple(a.action_type for a in decision.proposed_actions)
        out_of_scope = [
            c for c in dict.fromkeys(cited) if not self.rules.concerns(c, expected_role, actions)
        ]
        for clause_id in out_of_scope:  # decision 7n: same handling as unknown citations
            self._reject_decision(
                expected_role,
                Reason.CITATION_OUT_OF_SCOPE,
                (clause_id,),
                f"{expected_role} cited {clause_id}, concerning neither the role nor its action",
            )
        if out_of_scope:
            return
        claim_text = " ".join((decision.rationale, *decision.uncertainty))
        if not cited and GAP_CLAIM.search(claim_text):  # decision 7r
            self._reject_decision(
                expected_role,
                Reason.UNCITED_GAP_CLAIM,
                (),
                f"{expected_role} declared a legal gap without citing any clause",
            )
            return
        if decision.role_id != expected_role or decision.at != state.scenario.time_at(state.minute):
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
                self._apply(role, action, verdict)

    def _reject_decision(
        self, role: str, reason: Reason, clause_ids: tuple[str, ...], detail: str
    ) -> None:
        state = self.state
        state.record("rejected", role=role, reasons=(reason,), clause_ids=clause_ids, detail=detail)
        state.add_finding(
            Finding(
                kind=reason.value,
                minute=state.minute,
                role=role,
                clause_ids=clause_ids,
                detail=detail,
            )
        )

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
        if kind in (SHARE, REQUEST) and action.target == role.id:
            return Verdict(False, (Reason.SELF_TARGET,), (), "a role cannot target itself")
        fact_id: str | None = None
        if kind == SHARE:
            fact_id = action.parameters.get("fact", "")
            fact = state.fact(fact_id)
            if fact is None or fact not in state.known_facts(role.id):
                return Verdict(False, (Reason.FACT_NOT_KNOWN,), (), "sender does not know it")
            assert action.target is not None
            details.append(f"{fact.id} ({fact.data_category}) to {action.target}")
            if fact.data_category not in state.boundary(action.target):
                reasons.append(Reason.OUTSIDE_RECIPIENT_BOUNDARY)
            self._restrict(kind, fact.data_category, role.id, reasons, clause_ids, details)
        elif kind == REQUEST:
            category = action.parameters.get("data_category")
            if not category:
                return Verdict(False, (Reason.MISSING_PARAMETER,), (), "data_category is required")
            if category not in state.roles.known_categories():
                return Verdict(
                    False, (Reason.UNKNOWN_DATA_CATEGORY,), (), f"unknown category {category!r}"
                )
            details.append(f"{category} from {action.target}")
            self._restrict(kind, category, role.id, reasons, clause_ids, details)
        else:
            self._restrict(kind, None, role.id, reasons, clause_ids, details)

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
            authority, supporting = self.rules.authority(
                role.id, kind, spec.uncertain_authority_from
            )
            if authority is Authority.NONE:
                reasons.append(Reason.NO_AUTHORITY)
                details.append("no loaded clause gives this role authority")
            elif authority is Authority.UNCERTAIN:
                if Reason.AUTHORITY_UNCERTAIN not in reasons:
                    reasons.append(Reason.AUTHORITY_UNCERTAIN)
                details.append(REQUIRES_DETERMINATION)
            clause_ids.extend(supporting)
        return Verdict(not reasons, tuple(reasons), tuple(clause_ids), "; ".join(details), fact_id)

    def _restrict(
        self,
        kind: str,
        category: str | None,
        actor: str,
        reasons: list[Reason],
        clause_ids: list[str],
        details: list[str],
    ) -> None:
        """Unconditional bans reject outright; conditional ones (decision 7t) hold the action as
        authority uncertain - requires determination."""
        restricted = self.rules.restrictions(kind, category, actor)
        firm = [c for c in restricted if not self.rules.is_conditional(c)]
        conditional = [c for c in restricted if self.rules.is_conditional(c)]
        if firm:
            reasons.append(Reason.RESTRICTED_BY_CLAUSE)
        if conditional:
            reasons.append(Reason.AUTHORITY_UNCERTAIN)
            details.append(REQUIRES_DETERMINATION)
        clause_ids.extend(firm + conditional)

    def _apply(self, role: Role, action: ProposedAction, verdict: Verdict) -> None:
        state = self.state
        kind = action.action_type
        if kind == SHARE and action.target is not None and verdict.fact_id is not None:
            fact_id = verdict.fact_id  # exactly the fact that was checked
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
