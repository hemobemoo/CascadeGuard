"""What the engine records: per-step log entries, findings, and diagnosed coordination failures."""

from enum import StrEnum

from cascadeguard.domain.base import DomainModel


class FailureCategory(StrEnum):
    """The five failure categories of CascadeGuard.md section 4."""

    ORPHAN_DUTY = "orphan_duty"
    MANDATE_OVERLAP = "mandate_overlap"
    INFORMATION_DEADLOCK = "information_deadlock"
    TEMPORAL_INFEASIBILITY = "temporal_infeasibility"
    UNDEFINED_TRIGGER = "undefined_trigger"


class LogEntry(DomainModel):
    """One line of the append-only event log."""

    seq: int
    minute: int
    kind: str  # inject | fact_released | decision | accepted | rejected | obligation_* | goal_met
    role: str | None = None
    action: str | None = None
    target: str | None = None
    data_category: str | None = None  # the category a share or request touches
    detail: str = ""
    reasons: tuple[str, ...] = ()  # rejection reason codes
    clause_ids: tuple[str, ...] = ()


class Finding(DomainModel):
    """Something the engine noticed that is not itself a coordination failure."""

    kind: str  # unknown_citation | draft_citation | deadline_undetermined | trigger_not_loaded
    minute: int
    role: str | None = None
    clause_ids: tuple[str, ...] = ()
    detail: str


class CoordinationFailure(DomainModel):
    """A diagnosed failure. Never a confirmed legal gap: see `qualification`."""

    id: str  # "<category>:<subject>", stable across runs
    category: FailureCategory
    subject: str  # the action or data category the failure is about
    goals: tuple[str, ...]  # recovery goals it blocks
    roles: tuple[str, ...]
    clause_ids: tuple[str, ...]  # clauses considered (may be empty: nothing found)
    evidence: tuple[int, ...]  # log entry seq numbers
    description: str
    qualification: str
