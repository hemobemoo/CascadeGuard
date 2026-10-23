from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cascadeguard.domain.decisions import AgentDecision
from cascadeguard.domain.repairs import RepairOperationType, RepairProposal


def test_repair_grammar_is_the_closed_set_of_five() -> None:
    assert {op.value for op in RepairOperationType} == {
        "assign_owner",
        "add_escalation_trigger",
        "define_minimum_data_share",
        "add_fallback_channel",
        "designate_decision_requester",
    }


def test_free_text_repair_operation_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RepairProposal.model_validate(
            {
                "repair_id": "r1",
                "edits": [{"operation": "rewrite_the_law", "role": "telecom_operator"}],
                "rationale": "x",
                "citations": [],
            }
        )


def test_agent_decision_is_immutable() -> None:
    decision = AgentDecision(
        role_id="telecom_operator",
        at=datetime(2026, 3, 2, 4, 0, tzinfo=UTC),
        proposed_actions=(),
        rationale="monitoring",
        citations=(),
        uncertainty=(),
    )
    with pytest.raises(ValidationError):
        decision.role_id = "telecom_regulator"  # type: ignore[misc]
