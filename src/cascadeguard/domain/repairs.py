"""The closed repair grammar from CascadeGuard.md section 6. Do not add types without asking.

A repair is one or more edits. Each edit is one of the five operation types with fixed, typed
parameters; there is no free-text repair. Replay turns each edit into a hypothetical rule
(simulation/replay.py); it never changes a source clause.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, model_validator

from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.decisions import Citation

FALLBACK_ACTION = "activate_fallback_channel"
DETERMINATION_ACTION = "request_determination"
# Default deadline of an owner's obligation, in minutes after it opens (ADR 0002 option A).
OWNER_DEADLINE_MINUTES = 30
REPAIR_PREFIX = "repair."
REPAIR_LABEL = "hypothetical repair rule (not a source clause)"


class RepairOperationType(StrEnum):
    ASSIGN_OWNER = "assign_owner"
    ADD_ESCALATION_TRIGGER = "add_escalation_trigger"
    DEFINE_MINIMUM_DATA_SHARE = "define_minimum_data_share"
    ADD_FALLBACK_CHANNEL = "add_fallback_channel"
    DESIGNATE_DECISION_REQUESTER = "designate_decision_requester"


# Parameters each operation needs (beyond `role`) and what it may not carry.
_REQUIRED: dict[RepairOperationType, frozenset[str]] = {
    # role is made responsible for action (gives authority); its obligation opens when the
    # action's owner_obligation_opens_when first holds, due deadline_minutes later (ADR 0002 A)
    RepairOperationType.ASSIGN_OWNER: frozenset({"action", "deadline_minutes"}),
    # role must take action when trigger_event occurs, within deadline_minutes
    RepairOperationType.ADD_ESCALATION_TRIGGER: frozenset(
        {"action", "trigger_event", "deadline_minutes"}
    ),
    # role (sender) may share data_category with counterpart; widens counterpart's boundary
    RepairOperationType.DEFINE_MINIMUM_DATA_SHARE: frozenset({"data_category", "counterpart"}),
    # role must activate the fallback channel when trigger_event occurs
    RepairOperationType.ADD_FALLBACK_CHANNEL: frozenset(
        {"action", "trigger_event", "deadline_minutes"}
    ),
    # role must request a determination on `action` from counterpart when trigger_event occurs
    RepairOperationType.DESIGNATE_DECISION_REQUESTER: frozenset(
        {"action", "counterpart", "trigger_event", "deadline_minutes"}
    ),
}
_OPTIONAL = ("action", "data_category", "counterpart", "trigger_event", "deadline_minutes")


class RepairEdit(DomainModel):
    """One edit of the closed grammar, with typed parameters only."""

    operation: RepairOperationType
    role: str  # role the edit assigns, obliges or designates (the sender for a data share)
    action: str | None = None
    data_category: str | None = None
    counterpart: str | None = None  # share recipient, or the role asked for a determination
    trigger_event: str | None = None  # scenario event id that opens the new obligation
    deadline_minutes: int | None = Field(default=None, ge=0, strict=True)  # no coercion

    @model_validator(mode="before")
    @classmethod
    def _owner_default_deadline(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and data.get("operation") in (RepairOperationType.ASSIGN_OWNER, "assign_owner")  # pyright: ignore[reportUnknownMemberType]
            and data.get("deadline_minutes") is None  # pyright: ignore[reportUnknownMemberType]
        ):
            return {**data, "deadline_minutes": OWNER_DEADLINE_MINUTES}  # pyright: ignore[reportUnknownVariableType]
        return data  # pyright: ignore[reportUnknownVariableType]

    @model_validator(mode="after")
    def _check_parameters(self) -> Self:
        required = _REQUIRED[self.operation]
        missing = sorted(p for p in required if getattr(self, p) is None)
        extra = sorted(p for p in _OPTIONAL if p not in required and getattr(self, p) is not None)
        if missing or extra:
            raise ValueError(f"{self.operation.value}: missing {missing}, not allowed {extra}")
        if self.operation is RepairOperationType.ADD_FALLBACK_CHANNEL and (
            self.action != FALLBACK_ACTION
        ):
            raise ValueError(f"add_fallback_channel applies to {FALLBACK_ACTION} only")
        if self.counterpart is not None and self.counterpart == self.role:
            raise ValueError("counterpart must differ from role")
        return self

    @property
    def edit_id(self) -> str:
        """Stable id, also used in the hypothetical rule's clause id. It names every parameter,
        so two different edits never share an id."""
        op = self.operation
        when = f".{self.trigger_event}.{self.deadline_minutes}m" if self.trigger_event else ""
        if op is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:
            return f"share.{self.data_category}.{self.role}.{self.counterpart}"
        if op is RepairOperationType.DESIGNATE_DECISION_REQUESTER:
            return f"requester.{self.action}.{self.role}.{self.counterpart}{when}"
        if op is RepairOperationType.ASSIGN_OWNER:
            return f"owner.{self.action}.{self.role}.{self.deadline_minutes}m"
        prefix = {
            RepairOperationType.ADD_ESCALATION_TRIGGER: "trigger",
            RepairOperationType.ADD_FALLBACK_CHANNEL: "fallback",
        }[op]
        return f"{prefix}.{self.action}.{self.role}{when}"


class RepairProposal(DomainModel):
    repair_id: str  # the edit ids joined by "+", in canonical order
    edits: tuple[RepairEdit, ...] = Field(min_length=1)
    rationale: str
    citations: tuple[Citation, ...]
    requires_authorization: bool = False  # True if it creates a permission with no reviewed basis

    @model_validator(mode="after")
    def _check_id(self) -> Self:
        ids = [e.edit_id for e in self.edits]
        if len(set(ids)) != len(ids) or self.repair_id != "+".join(sorted(ids)):
            raise ValueError("repair_id must be the sorted, distinct edit ids joined by '+'")
        return self
