"""Engine rules from the human decisions of 2026-10-23: 7n, 7r, 7t/7v, h2, 7m, 7u."""

from typing import Any

import pytest
from pydantic import ValidationError

from cascadeguard.domain.decisions import (
    GAP_QUALIFICATION,
    AgentDecision,
    Citation,
    GapClaim,
    ProposedAction,
)
from cascadeguard.domain.policies import ClauseStatus, PolicyClause
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import Authority, ConstraintEngine, Reason, RuleBook
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.loader import load_scenario
from cascadeguard.simulation.state import SimulationState

HEALTH, TELECOM, OVERSIGHT = "health_service_operator", "telecom_operator", "health_data_oversight"


def clause(cid: str, binding: Any = False, status: str = "illustrative", **n: Any) -> PolicyClause:
    data: dict[str, Any] = {
        "id": cid,
        "title": cid,
        "text": "Synthetic test clause.",
        "issuer": "i",
        "jurisdiction": "j",
        "document_date": "unknown",
        "status": status,
        "binding": binding,
        "notes": "n",
        "normalized": {"basis": "stated", **n},
    }
    if status != "illustrative":
        data |= {"source_file": "doc.pdf", "page": 1}
    return PolicyClause.model_validate(data)


@pytest.fixture(scope="module")
def world() -> tuple[Scenario, RoleSet]:
    return load_scenario("uae_health_access", {c.id for c in load_clauses()})


def engine_at(
    world: tuple[Scenario, RoleSet], minute: int, *rules: PolicyClause
) -> ConstraintEngine:
    scenario, roles = world
    engine = ConstraintEngine(
        SimulationState(scenario, roles), {c.id: c for c in rules}, frozenset(c.id for c in rules)
    )
    for event in scenario.events:
        if event.at_minute <= minute:
            engine.release(event)
    return engine


def decide(
    world: tuple[Scenario, RoleSet],
    role: str,
    minute: int,
    *actions: str,
    cite: tuple[str, ...] = (),
    rationale: str = "x",
) -> AgentDecision:
    return AgentDecision(
        role_id=role,
        at=world[0].time_at(minute),
        proposed_actions=tuple(ProposedAction(action_type=a) for a in actions),
        rationale=rationale,
        citations=tuple(Citation(clause_id=c, relevance="x") for c in cite),
        uncertainty=(),
    )


def decision_findings(engine: ConstraintEngine) -> list[str]:
    return [f.kind for f in engine.state.findings if f.kind != "trigger_not_loaded"]


# ---- 7t: conditional prohibitions hold the action as "authority uncertain" ----


def test_a_conditional_prohibition_requires_a_determination(
    world: tuple[Scenario, RoleSet],
) -> None:
    conditional = clause(
        "c.ban",
        kind="prohibition",
        actor="any",
        action="raise_security_incident",
        condition="unless an exception applies",
    )
    engine = engine_at(world, 15, conditional)
    verdict = engine.check(
        world[1].role(HEALTH), ProposedAction(action_type="raise_security_incident")
    )
    assert verdict.reasons == (Reason.AUTHORITY_UNCERTAIN,)
    assert "requires determination" in verdict.detail
    assert verdict.clause_ids == ("c.ban",)


def test_an_unconditional_prohibition_still_rejects_outright(
    world: tuple[Scenario, RoleSet],
) -> None:
    flat = clause("f.ban", kind="prohibition", actor="any", action="raise_security_incident")
    engine = engine_at(world, 15, flat)
    verdict = engine.check(
        world[1].role(HEALTH), ProposedAction(action_type="raise_security_incident")
    )
    assert verdict.reasons == (Reason.RESTRICTED_BY_CLAUSE,)


def test_real_art4_and_art16_are_conditional_prohibitions() -> None:
    clauses = load_engine_clauses()
    rules = RuleBook(clauses)
    for cid in ("uae.fl2-2019.art4", "uae.fl2-2019.art16"):
        normalized = clauses[cid].normalized
        assert normalized is not None
        assert normalized.kind == "prohibition"
        assert rules.is_conditional(cid), cid


# ---- 7v / 7m: conditional permissions give only uncertain authority ----


@pytest.mark.parametrize("binding", [True, False])
def test_a_conditional_permission_gives_only_uncertain_authority(binding: bool) -> None:
    status = "reviewed" if binding else "illustrative"
    rules = RuleBook(
        {
            "p": clause(
                "p",
                binding,
                status,
                kind="permission",
                actor=OVERSIGHT,
                action="issue_determination",
                condition="on a matter in its remit",
            )
        }
    )
    assert rules.authority(OVERSIGHT, "issue_determination")[0] is Authority.UNCERTAIN


def test_real_art6_gives_uncertain_authority_and_art14_5_none() -> None:
    corpus = {c.id: c for c in load_clauses()}
    rules = RuleBook(corpus)
    assert rules.authority(OVERSIGHT, "issue_determination") == (
        Authority.UNCERTAIN,
        ("uae.fl2-2019.art6",),
    )
    # Human decision 2026-10-24: art14-5 has no action mapping (a power to issue rules, 7m),
    # so it gives the regulator no authority to request information on its own.
    art14 = corpus["uae.telecom-law.art14-5"]
    assert art14.normalized is None
    rules = RuleBook({art14.id: art14})
    assert rules.authority("telecom_regulator", "request_information")[0] is Authority.NONE


# ---- h2: a duty to keep a fallback plan implies only uncertain activation authority ----


def test_fallback_plan_duty_implies_only_uncertain_activation_authority(
    world: tuple[Scenario, RoleSet],
) -> None:
    plan = clause("plan", kind="obligation", actor=HEALTH, action="maintain_fallback_plan")
    engine = engine_at(world, 60, plan)
    verdict = engine.check(
        world[1].role(HEALTH), ProposedAction(action_type="activate_fallback_channel")
    )
    assert verdict.reasons == (Reason.AUTHORITY_UNCERTAIN,)
    assert verdict.clause_ids == ("plan",)
    without = engine_at(world, 60)
    bare = without.check(
        world[1].role(HEALTH), ProposedAction(action_type="activate_fallback_channel")
    )
    assert bare.reasons == (Reason.NO_AUTHORITY,)


def test_real_4_18_1_maps_to_maintaining_a_plan_not_activating() -> None:
    n = load_engine_clauses()["dha.pp11.4-18-1"].normalized
    assert n is not None and n.action == "maintain_fallback_plan"


# ---- 7n: a citation must concern the citing role or its action ----


def test_out_of_scope_citation_rejects_the_decision(world: tuple[Scenario, RoleSet]) -> None:
    telecom_rule = clause(
        "t.rule", kind="obligation", actor=TELECOM, action="report_to_telecom_regulator"
    )
    engine = engine_at(world, 15, telecom_rule)
    engine.process(decide(world, HEALTH, 15, "raise_security_incident", cite=("t.rule",)), HEALTH)
    assert decision_findings(engine) == ["citation_out_of_scope"]
    assert not engine.state.has_done(HEALTH, "raise_security_incident")


@pytest.mark.parametrize(
    ("rule", "action"),
    [
        ({"actor": HEALTH, "action": "notify_health_data_oversight"}, "raise_security_incident"),
        ({"actor": "any", "action": "share_incident_status"}, "raise_security_incident"),
        ({"actor": TELECOM, "action": "raise_security_incident"}, "raise_security_incident"),
    ],
)
def test_in_scope_citations_are_accepted(
    world: tuple[Scenario, RoleSet], rule: dict[str, str], action: str
) -> None:
    engine = engine_at(world, 15, clause("r", kind="obligation", **rule))
    engine.process(decide(world, HEALTH, 15, action, cite=("r",)), HEALTH)
    assert decision_findings(engine) == []
    assert engine.state.has_done(HEALTH, action)


def test_policy_analysis_may_cite_any_loaded_clause(world: tuple[Scenario, RoleSet]) -> None:
    other = clause("t.rule", kind="obligation", actor=TELECOM, action="report_to_telecom_regulator")
    engine = engine_at(world, 45, other)
    adviser = "policy_legal_adviser"
    engine.process(decide(world, adviser, 45, "provide_policy_analysis", cite=("t.rule",)), adviser)
    assert decision_findings(engine) == []


# ---- 7r: legal-gap claims need citations ----


@pytest.mark.parametrize(
    "text",
    ["CONFIRMED LEGAL GAP: UAE law has no provision on this.", "There is a regulatory gap here."],
)
def test_uncited_gap_claim_rejects_the_decision(world: tuple[Scenario, RoleSet], text: str) -> None:
    engine = engine_at(world, 45)
    adviser = "policy_legal_adviser"
    engine.process(decide(world, adviser, 45, "provide_policy_analysis", rationale=text), adviser)
    assert decision_findings(engine) == ["uncited_gap_claim"]
    assert not engine.state.has_done(adviser, "provide_policy_analysis")


def gap_claim(statement: str, *cite: str) -> GapClaim:
    return GapClaim(
        statement=statement,
        citations=tuple(Citation(clause_id=c, relevance="x") for c in cite),
        qualification=GAP_QUALIFICATION,
    )


def test_a_structured_gap_claim_is_accepted_and_kept_as_a_candidate(
    world: tuple[Scenario, RoleSet],
) -> None:
    rule = clause("r", kind="obligation", actor=HEALTH, action="raise_security_incident")
    engine = engine_at(world, 45, rule)
    adviser = "policy_legal_adviser"
    decision = decide(world, adviser, 45, "provide_policy_analysis", rationale="Analysis.")
    claim = gap_claim("No loaded clause assigns review of automated lockouts.", "r")
    engine.process(decision.model_copy(update={"gap_claims": (claim,)}), adviser)
    assert decision_findings(engine) == ["candidate_gap_claim"]
    assert engine.state.has_done(adviser, "provide_policy_analysis")
    assert GAP_QUALIFICATION in engine.state.findings[-1].detail


@pytest.mark.parametrize(
    "bad",
    [
        {"citations": ()},  # a gap claim must cite
        {"qualification": "confirmed legal gap"},  # only the fixed qualification
        {"qualification": "not a candidate finding"},
    ],
)
def test_gap_claim_schema_requires_citations_and_the_fixed_qualification(
    bad: dict[str, Any],
) -> None:
    data = gap_claim("No clause found.", "r").model_dump() | bad
    with pytest.raises(ValidationError):
        GapClaim.model_validate(data)


def test_a_gap_claim_stated_as_certain_is_rejected(world: tuple[Scenario, RoleSet]) -> None:
    rule = clause("r", kind="obligation", actor=HEALTH, action="raise_security_incident")
    engine = engine_at(world, 45, rule)
    adviser = "policy_legal_adviser"
    decision = decide(world, adviser, 45, "provide_policy_analysis", rationale="Analysis.")
    claim = gap_claim("UAE law definitively has no rule on this.", "r")
    engine.process(decision.model_copy(update={"gap_claims": (claim,)}), adviser)
    assert decision_findings(engine) == ["overstated_gap_claim"]
    assert not engine.state.has_done(adviser, "provide_policy_analysis")


# ---- 7u: binding: unknown on an illustrative clause is for fixtures only ----


def test_real_clauses_never_use_binding_unknown_on_illustrative_rules() -> None:
    """In policies/reviewed, binding: unknown appears only on draft (agent proposal awaiting the
    human) or reviewed (set by the human) clauses, never on illustrative ones."""
    for c in load_clauses():
        if c.binding == "unknown":
            assert c.status in (ClauseStatus.DRAFT, ClauseStatus.REVIEWED), c.id


# ---- Phase 3 review round 1: bypasses of 7n and 7r ----


@pytest.mark.parametrize("extra", ["provide_policy_analysis", "issue_determination"])
def test_a_disallowed_action_does_not_widen_citation_scope(
    world: tuple[Scenario, RoleSet], extra: str
) -> None:
    """Adding an action the role may not take (even provide_policy_analysis) must not make an
    out-of-scope citation acceptable."""
    rule = clause("h.rule", kind="obligation", actor=OVERSIGHT, action=extra)
    engine = engine_at(world, 45, rule)
    engine.process(decide(world, TELECOM, 45, "monitor", extra, cite=("h.rule",)), TELECOM)
    assert decision_findings(engine) == ["citation_out_of_scope"]
    assert not engine.state.has_done(TELECOM, "monitor")


@pytest.mark.parametrize(
    "text",
    [
        "The law is silent on who may reverse the locks.",
        "No clause authorises this; nothing in the regulations covers it.",
        "Lacuna: unregulated area",
        "No clause found that authorises this share.",
        "This is not covered by any rule.",
    ],
)
def test_gap_claims_in_other_words_still_need_citations(
    world: tuple[Scenario, RoleSet], text: str
) -> None:
    engine = engine_at(world, 45)
    engine.process(
        decide(world, TELECOM, 45, "report_to_telecom_regulator", rationale=text), TELECOM
    )
    assert decision_findings(engine) == ["uncited_gap_claim"]


@pytest.mark.parametrize(
    "text",
    [
        "There is a legal gap here, definitely.",
        # Phase 3 review round 2: a negated qualifier or a paraphrase must not pass.
        "This is not a candidate finding: UAE law has a confirmed legal gap on fallback "
        "activation.",
        "The statute is silent about who activates the fallback channel; this is definitively a "
        "hole in UAE law.",
        "UAE legislation does not cover fallback activation at all; confirmed.",
        "Candidate finding: no provision on lockout review was found in the reviewed corpus.",
    ],
)
def test_gap_wording_in_free_text_is_rejected_even_when_cited(
    world: tuple[Scenario, RoleSet], text: str
) -> None:
    """A gap may be stated only in a GapClaim; cited free text does not make it acceptable."""
    rule = clause("r", kind="obligation", actor=TELECOM, action="report_to_telecom_regulator")
    engine = engine_at(world, 45, rule)
    engine.process(
        decide(world, TELECOM, 45, "report_to_telecom_regulator", cite=("r",), rationale=text),
        TELECOM,
    )
    assert decision_findings(engine) == ["uncited_gap_claim"]
    assert not engine.state.has_done(TELECOM, "report_to_telecom_regulator")


def test_loaded_clauses_outside_the_corpus_are_not_citable(
    world: tuple[Scenario, RoleSet],
) -> None:
    """A hypothetical repair rule is loaded in a replay but is not a policies/reviewed clause."""
    scenario, roles = world
    rule = clause(
        "repair.owner.review_automated_lockouts.health_service_operator",
        kind="obligation",
        actor=HEALTH,
        action="review_automated_lockouts",
    )
    engine = ConstraintEngine(SimulationState(scenario, roles), {rule.id: rule}, frozenset())
    for event in scenario.events:
        if event.at_minute <= 45:
            engine.release(event)
    engine.process(decide(world, HEALTH, 45, "review_automated_lockouts", cite=(rule.id,)), HEALTH)
    assert decision_findings(engine) == ["unknown_citation"]
    assert not engine.state.has_done(HEALTH, "review_automated_lockouts")
