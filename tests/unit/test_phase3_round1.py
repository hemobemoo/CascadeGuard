"""Regression tests for the Phase 3 review round 1 findings (repair search, replay, exports)."""

from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError

from cascadeguard.agents.scripted import load_scripted_agents
from cascadeguard.cli import format_search, load_world
from cascadeguard.domain.decisions import Citation
from cascadeguard.domain.findings import LogEntry
from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.repairs import RepairEdit, RepairProposal
from cascadeguard.engine.constraints import AGENT_STATEMENT, RuleBook
from cascadeguard.engine.repair_search import (
    ReplayComparison,
    SearchResult,
    _restricted_by,  # pyright: ignore[reportPrivateUsage]
    proposal,
    rank_key,
    search,
)
from cascadeguard.simulation.loader import SCENARIOS_DIR
from cascadeguard.simulation.replay import apply_repair
from cascadeguard.storage.audit import AuditStore
from cascadeguard.storage.export import comparison_export, run_export, search_export

HEALTH, TELECOM = "health_service_operator", "telecom_operator"
SHARE: dict[str, Any] = {
    "operation": "define_minimum_data_share",
    "role": TELECOM,
    "counterpart": HEALTH,
    "data_category": "network_incident_status",
}
OWNER: dict[str, Any] = {
    "operation": "assign_owner",
    "role": HEALTH,
    "action": "reverse_automated_lockouts",
}
TRIGGER: dict[str, Any] = {
    "operation": "add_escalation_trigger",
    "role": HEALTH,
    "action": "review_automated_lockouts",
    "trigger_event": "t45_responsibilities_diverge",
    "deadline_minutes": 15,
}


def rule(cid: str, status: str = "illustrative", binding: Any = False, **n: Any) -> PolicyClause:
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


# ---- hard filter: the widened boundary, not only the named sender ----


def test_share_edit_is_checked_for_every_sender_not_only_the_named_one() -> None:
    w = load_world("uae_health_access")
    ban = rule(
        "syn.ban",
        kind="prohibition",
        actor=HEALTH,
        action="share_incident_status",
        data_category="auth_service_metrics",
    )
    rules = RuleBook({**w.clauses, ban.id: ban})
    edit = RepairEdit.model_validate(
        {
            "operation": "define_minimum_data_share",
            "role": "health_data_oversight",  # not the holder, not the banned actor
            "counterpart": TELECOM,
            "data_category": "auth_service_metrics",
        }
    )
    # The edit names a sender no clause restricts, but the widened boundary lets the
    # category arrive from the banned health operator too, so it is restricted.
    assert _restricted_by(edit, rules, w.roles) == ("syn.ban",)
    assert _restricted_by(edit, RuleBook(w.clauses), w.roles) == ()


def test_a_replay_that_delivers_a_restricted_category_to_a_new_role_is_discarded() -> None:
    w = load_world("uae_health_access")
    from cascadeguard.simulation.replay import replay

    def leaky(p: RepairProposal) -> Any:
        result = replay(w.scenario, w.roles, w.clauses, w.corpus_ids, w.agents, w.label, p)
        leak = LogEntry(
            seq=len(result.log),
            minute=75,
            kind="fact_released",
            role="public_access_inclusion",
            detail="locked_account_records",
        )
        return replace(result, log=(*result.log, leak))

    result = search(w.baseline(), w.scenario, w.roles, RuleBook(w.clauses), leaky)
    assert not result.ranked
    assert all(
        {"uae.fl2-2019.art4", "uae.fl2-2019.art16"} <= set(d.clause_ids) for d in result.discarded
    )


# ---- requires_authorization matches the share's roles and conditions ----


@pytest.mark.parametrize(
    ("basis", "needs"),
    [
        ({"actor": "telecom_regulator", "counterpart": "public_access_inclusion"}, True),
        ({"actor": TELECOM, "counterpart": HEALTH, "condition": "if the minister decides"}, True),
        # Covers only the named sender; the regulator could also send once the boundary widens.
        ({"actor": TELECOM, "counterpart": HEALTH}, True),
        ({"actor": "any"}, False),
    ],
)
def test_share_needs_authorization_unless_a_matching_unconditional_reviewed_clause(
    basis: dict[str, Any], needs: bool
) -> None:
    w = load_world("uae_health_access")
    permit = rule(
        "syn.permit",
        status="reviewed",
        binding=True,
        kind="permission",
        action="share_incident_status",
        data_category="network_incident_status",
        **basis,
    )
    rules = RuleBook({**w.clauses, permit.id: permit})
    p = proposal((RepairEdit.model_validate(SHARE),), {}, rules, w.roles)
    assert p.requires_authorization is needs


# ---- repair ids, re-validation, agents ----


def test_edits_with_different_triggers_have_different_ids() -> None:
    a = RepairEdit.model_validate(TRIGGER)
    b = RepairEdit.model_validate(
        {**TRIGGER, "trigger_event": "t15_fraud_model_locks_accounts", "deadline_minutes": 15}
    )
    c = RepairEdit.model_validate({**TRIGGER, "deadline_minutes": 30})
    assert len({a.edit_id, b.edit_id, c.edit_id}) == 3


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_replay_revalidates_the_proposal() -> None:
    w = load_world("uae_health_access")
    good = proposal((RepairEdit.model_validate(OWNER),), {}, RuleBook(w.clauses), w.roles)
    forged = good.model_copy(
        update={"edits": (good.edits[0].model_copy(update={"operation": "rewrite_the_law"}),)}
    )
    with pytest.raises(ValidationError):
        apply_repair(w.scenario, w.roles, w.clauses, forged)


def test_repair_edit_must_name_an_action_the_role_may_take() -> None:
    w = load_world("uae_health_access")
    bad = RepairEdit.model_validate({**OWNER, "role": TELECOM})
    with pytest.raises(ValueError, match="may not"):
        apply_repair(w.scenario, w.roles, w.clauses, proposal((bad,), {}, RuleBook({}), w.roles))


def test_scripted_agent_output_never_aliases_shared_data() -> None:
    w = load_world("uae_health_access")
    agents = load_scripted_agents(
        SCENARIOS_DIR / "uae_health_access" / "scripted_decisions.yaml", w.scenario, w.roles
    )
    baseline = w.baseline().summary()
    original = agents[TELECOM].observe
    calls: list[int] = []

    def tampering(view: Any) -> Any:
        decision = original(view)
        for action in decision.proposed_actions:
            action.parameters["fact"] = "locked_account_records"
        calls.append(1)
        return decision

    agents[TELECOM].observe = tampering  # type: ignore[method-assign]
    w2 = replace(w, agents=agents)
    w2.baseline()
    assert calls
    agents[TELECOM].observe = original  # type: ignore[method-assign]
    assert replace(w, agents=agents).baseline().summary() == baseline


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("2020-13-45", False),
        ("2021-02-30", False),
        ("2024-02-29", True),
        ("2024-07", True),
        ("2024", True),
        ("unknown", True),
    ],
)
def test_document_date_must_be_a_real_date(value: str, ok: bool) -> None:
    data = rule("x", kind="obligation", actor=HEALTH, action="monitor").model_dump(mode="python")
    data["document_date"] = value
    if ok:
        assert PolicyClause.model_validate(data).document_date == value
    else:
        with pytest.raises(ValidationError):
            PolicyClause.model_validate(data)


# ---- ranking tie-breaks ----


def _comparison(w: Any, edits: tuple[dict[str, Any], ...], cites: int = 0) -> ReplayComparison:
    p = proposal(
        tuple(RepairEdit.model_validate(e) for e in edits), {}, RuleBook(w.clauses), w.roles
    )
    p = p.model_copy(
        update={
            "citations": tuple(Citation(clause_id=f"c{i}", relevance="x") for i in range(cites))
        }
    )
    base = w.baseline()
    return ReplayComparison(p, base, base, ())


def test_ranking_tie_breaks_in_order() -> None:
    w = load_world("uae_health_access")
    owner = _comparison(w, (OWNER,))  # 1 role, requires authorization
    trigger = _comparison(w, (TRIGGER,))  # 1 role, no authorization needed
    share = _comparison(w, (SHARE,))  # 2 roles, requires authorization
    owner_cited = _comparison(w, (OWNER,), cites=2)
    pair = _comparison(w, (TRIGGER, OWNER))  # more edits
    ordered = sorted([pair, share, owner_cited, owner, trigger], key=rank_key)
    assert ordered == [trigger, owner, owner_cited, share, pair]


# ---- labels and qualifications everywhere ----


def test_search_output_keeps_labels_when_every_repair_is_discarded() -> None:
    w = load_world("uae_health_access")
    empty = SearchResult(w.label, w.baseline().loaded_clauses, (), ())
    text = format_search(empty)
    assert f"Clause set: {w.label}" in text
    assert "no candidate repair passed the hard filter" in text
    fixtures = load_world("uae_health_access", SCENARIOS_DIR.parent / "tests/fixtures/clauses")
    assert "SYNTHETIC FIXTURES" in format_search(SearchResult(fixtures.label, (), (), ()))


def test_json_exports_label_every_clause_and_keep_qualifications() -> None:
    from cascadeguard.cli import search_repairs

    found = search_repairs("uae_health_access")
    base = run_export(found.ranked[0].baseline)
    assert all(set(f) >= {"qualification", "description"} for f in base["failures"])
    for f in base["failures"]:
        assert "not a confirmed legal or standards gap" in f["qualification"]
    assert {"id": "dha.pp11.4-18-1", "status": "reviewed (interpreted)"} in [
        c for f in base["failures"] for c in f["clauses"]
    ]
    assert all("status" in c for e in base["rejected_decisions"] for c in e.get("clauses", []))
    search_json = search_export(found)
    assert search_json["clause_set"] == found.clause_set
    assert {"id": "uae.fl2-2019.art4", "status": "reviewed (interpreted)"} in search_json[
        "discarded"
    ][0]["clauses"]
    replay_json = comparison_export(
        found.comparison("share.network_incident_status.telecom_operator.health_service_operator")
    )
    for f in replay_json["failures_remaining"] + replay_json["failures_removed"]:
        assert "qualification" in f and all("status" in c for c in f["clauses"])


# ---- Phase 3 review round 2 ----


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "waive_art4_and_send_patient_records_to_telecom"},  # not a scenario action
        {"counterpart": TELECOM},  # issues no determinations
    ],
)
def test_decision_requester_parameters_are_checked(bad: dict[str, Any]) -> None:
    w = load_world("uae_health_access")
    edit = RepairEdit.model_validate(
        {
            "operation": "designate_decision_requester",
            "role": HEALTH,
            "action": "activate_fallback_channel",
            "counterpart": "health_data_oversight",
            "trigger_event": "t60_public_access_affected",
            "deadline_minutes": 15,
            **bad,
        }
    )
    with pytest.raises(ValueError, match=r"may not|issues no determinations"):
        apply_repair(w.scenario, w.roles, w.clauses, proposal((edit,), {}, RuleBook({}), w.roles))


@pytest.mark.parametrize("value", [True, "15", 15.0])
def test_deadline_is_a_strict_integer(value: Any) -> None:
    with pytest.raises(ValidationError):
        RepairEdit.model_validate({**TRIGGER, "deadline_minutes": value})


def test_a_later_agent_cannot_alter_an_earlier_decision_in_the_same_step() -> None:
    w = load_world("uae_health_access")
    expected = w.baseline().summary()
    returned: list[Any] = []

    def wrap(agent: Any) -> Any:
        class Tamperer:
            def observe(self, view: Any) -> Any:
                for d in returned:  # alter every decision handed in so far
                    for a in d.proposed_actions:
                        a.parameters["fact"] = "locked_account_records"
                decision = agent.observe(view)
                returned.append(decision)
                return decision

        return Tamperer()

    tampering = {rid: wrap(a) for rid, a in w.agents.items()}
    assert replace(w, agents=tampering).baseline().summary() == expected


# ---- Phase 3 review round 3 (fixed after the last round; not re-reviewed) ----


@pytest.mark.parametrize(
    "text",
    [
        "UAE law lacks any provision on who may reverse automated lockouts; this omission is "
        "definitive.",
        "The legislation is entirely mute on lock reversal, so nobody is legally empowered.",
        "Federal law contains no statute assigning this duty; it is a legislative void.",
    ],
)
def test_agent_free_text_is_stored_only_as_a_labelled_agent_statement(
    tmp_path: Any, text: str
) -> None:
    """Wording the gap pattern misses is never a finding and never stored unlabelled."""
    w = load_world("uae_health_access")
    adviser = "policy_legal_adviser"

    class Adviser:
        def observe(self, view: Any) -> Any:
            return w.agents[adviser].observe(view).model_copy(update={"rationale": text})

    result = replace(w, agents={**w.agents, adviser: Adviser()}).baseline()  # type: ignore[dict-item]
    statements = [e.detail for e in result.log if e.kind == "decision" and text in e.detail]
    assert statements
    assert all(d == f"{AGENT_STATEMENT}{text}" for d in statements)
    assert not any(text in f.detail for f in result.findings)
    store = AuditStore(tmp_path / "a.duckdb")
    try:
        store.record_run(result, "baseline")
        rows = store.con.execute(
            "SELECT detail FROM events WHERE kind = 'decision' AND detail LIKE ?", [f"%{text}%"]
        ).fetchall()
    finally:
        store.close()
    assert rows and all(r[0].startswith(AGENT_STATEMENT) for r in rows)


def test_requester_needs_authorization_when_requesting_requires_authority() -> None:
    w = load_world("uae_health_access")
    actions = tuple(
        a.model_copy(update={"requires_authority": True}) if a.id == "request_determination" else a
        for a in w.roles.actions
    )
    roles = w.roles.model_copy(update={"actions": actions})
    edit = RepairEdit.model_validate(
        {
            "operation": "designate_decision_requester",
            "role": HEALTH,
            "action": "activate_fallback_channel",
            "counterpart": "health_data_oversight",
            "trigger_event": "t60_public_access_affected",
            "deadline_minutes": 15,
        }
    )
    assert proposal((edit,), {}, RuleBook(w.clauses), roles).requires_authorization is True
    assert proposal((edit,), {}, RuleBook(w.clauses), w.roles).requires_authorization is False
