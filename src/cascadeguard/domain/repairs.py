"""The closed repair grammar from CascadeGuard.md section 6. Do not add types without asking."""

from enum import StrEnum

from pydantic import Field

from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.decisions import Citation


class RepairOperationType(StrEnum):
    ASSIGN_OWNER = "assign_owner"
    ADD_ESCALATION_TRIGGER = "add_escalation_trigger"
    DEFINE_MINIMUM_DATA_SHARE = "define_minimum_data_share"
    ADD_FALLBACK_CHANNEL = "add_fallback_channel"
    DESIGNATE_DECISION_REQUESTER = "designate_decision_requester"


class RepairProposal(DomainModel):
    repair_id: str
    operation: RepairOperationType
    applies_to: list[str]  # role ids / clause ids / graph edges affected
    parameters: dict[str, str] = Field(default_factory=dict)
    rationale: str
    citations: list[Citation]
    requires_authorization: bool = False  # True if it creates a permission with no reviewed basis
