"""The closed repair grammar: typed parameters only, canonical ids, immutable proposals."""

from typing import Any

import pytest
from pydantic import ValidationError

from cascadeguard.domain.policies import PolicyClause
from cascadeguard.domain.repairs import RepairEdit, RepairOperationType, RepairProposal
from cascadeguard.domain.scenario import RoleSet, Scenario
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.engine.repair_search import proposal
from cascadeguard.knowledge.loader import load_clauses, load_engine_clauses
from cascadeguard.simulation.loader import ScenarioLoadError, load_scenario
from cascadeguard.simulation.replay import apply_repair

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
FALLBACK: dict[str, Any] = {
    "operation": "add_fallback_channel",
    "role": HEALTH,
    "action": "activate_fallback_channel",
    "trigger_event": "t60_public_access_affected",
    "deadline_minutes": 15,
}
REQUESTER: dict[str, Any] = {
    "operation": "designate_decision_requester",
    "role": HEALTH,
    "action": "activate_fallback_channel",
    "counterpart": "health_data_oversight",
    "trigger_event": "t60_public_access_affected",
    "deadline_minutes": 15,
}


@pytest.mark.parametrize(
    "edit",
    [
        {"operation": "assign_owner", "role": HEALTH},  # missing action
        {**OWNER, "data_category": "network_incident_status"},  # parameter it may not carry
        {**SHARE, "counterpart": TELECOM},  # sharing with itself
        {**FALLBACK, "action": "reverse_automated_lockouts"},  # fallback edits name one action
        {**OWNER, "rationale": "free text"},  # unknown field
        {**TRIGGER, "deadline_minutes": -1},
    ],
)
def test_malformed_edits_are_rejected(edit: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RepairEdit.model_validate(edit)


def test_repair_id_must_be_the_canonical_edit_ids() -> None:
    edits = [SHARE, OWNER]
    good = "+".join(sorted(RepairEdit.model_validate(e).edit_id for e in edits))
    base: dict[str, Any] = {"edits": edits, "rationale": "x", "citations": []}
    assert RepairProposal.model_validate({**base, "repair_id": good}).repair_id == good
    with pytest.raises(ValidationError):
        RepairProposal.model_validate({**base, "repair_id": "best-repair"})
    with pytest.raises(ValidationError):
        RepairProposal.model_validate({**base, "edits": [], "repair_id": ""})


def test_proposals_are_deeply_immutable() -> None:
    p = RepairProposal.model_validate(
        {
            "repair_id": RepairEdit.model_validate(OWNER).edit_id,
            "edits": [OWNER],
            "rationale": "x",
            "citations": [],
        }
    )
    assert isinstance(p.edits, tuple)
    assert isinstance(p.citations, tuple)
    with pytest.raises(ValidationError):
        p.edits[0].role = TELECOM  # type: ignore[misc]


def _world() -> tuple[Scenario, RoleSet, dict[str, PolicyClause]]:
    scenario, roles = load_scenario("uae_health_access", {c.id for c in load_clauses()})
    return scenario, roles, load_engine_clauses()


def _proposal(*edits: dict[str, Any]) -> RepairProposal:
    _, roles, clauses = _world()
    parsed = tuple(RepairEdit.model_validate(e) for e in edits)
    return proposal(parsed, {}, RuleBook(clauses), roles)


def test_apply_repair_changes_only_what_the_edits_name() -> None:
    scenario, roles, clauses = _world()
    s, r, c = apply_repair(scenario, roles, clauses, _proposal(SHARE, TRIGGER))
    assert set(c) - set(clauses) == {
        "repair.share.network_incident_status.telecom_operator.health_service_operator",
        "repair.trigger.review_automated_lockouts.health_service_operator",
    }
    assert {k: c[k] for k in clauses} == clauses
    assert r.role(HEALTH).boundary.visible_categories[-1] == "network_incident_status"
    assert [x for x in r.roles if x.id != HEALTH] == [x for x in roles.roles if x.id != HEALTH]
    changed = [e.id for e, old in zip(s.events, scenario.events, strict=True) if e != old]
    assert changed == ["t45_responsibilities_diverge"]
    # The inputs are untouched.
    assert "network_incident_status" not in roles.role(HEALTH).boundary.visible_categories


def test_apply_repair_rejects_unknown_events_and_roles() -> None:
    scenario, roles, clauses = _world()
    with pytest.raises(ValueError, match="unknown trigger events"):
        apply_repair(scenario, roles, clauses, _proposal({**TRIGGER, "trigger_event": "t99_never"}))
    with pytest.raises(ScenarioLoadError):
        apply_repair(scenario, roles, clauses, _proposal({**OWNER, "role": "ministry_of_magic"}))


@pytest.mark.parametrize(
    ("edit", "needs"),
    [
        (SHARE, True),  # no reviewed clause permits this share
        (OWNER, True),  # no reviewed clause gives authority to reverse locks
        (FALLBACK, True),  # dha.pp11.4-18-1 implies only uncertain activation authority (h2)
        (TRIGGER, False),  # review needs no authority
        (REQUESTER, False),  # asking for a determination grants no permission
    ],
)
def test_requires_authorization_when_no_reviewed_clause_supports_a_new_permission(
    edit: dict[str, Any], needs: bool
) -> None:
    assert _proposal(edit).requires_authorization is needs


def test_every_operation_type_becomes_a_typed_rule() -> None:
    scenario, roles, clauses = _world()
    edits = (SHARE, OWNER, TRIGGER, FALLBACK, REQUESTER)
    assert {e["operation"] for e in edits} == {op.value for op in RepairOperationType}
    _, _, c = apply_repair(scenario, roles, clauses, _proposal(*edits))
    rules = {cid: rule for cid, rule in c.items() if cid.startswith("repair.")}
    kinds = sorted(r.normalized.kind.value for r in rules.values() if r.normalized is not None)
    assert kinds == ["obligation"] * 4 + ["permission"]
    for rule in rules.values():
        assert rule.status.value == "illustrative"
        assert rule.text.startswith("Hypothetical repair rule, not a quotation")
