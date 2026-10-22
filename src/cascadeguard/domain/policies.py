"""Policy clauses extracted from the PDFs in policies/sources/ (see AGENTS.md)."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from cascadeguard.domain.base import DomainModel

ELISION = "[...]"  # marks an omission inside a verbatim quote
CLAUSE_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
# Year, year-month, full ISO date, or "unknown" when the PDF prints no date (never guessed).
DOCUMENT_DATE_PATTERN = r"^(\d{4}(-\d{2}(-\d{2})?)?|unknown)$"


class ClauseStatus(StrEnum):
    DRAFT = "draft"  # drafted by an agent, not yet checked against the PDF
    REVIEWED = "reviewed"  # checked by the human against the PDF
    ILLUSTRATIVE = "illustrative"  # needed by the scenario but not supported by any source PDF


class RuleKind(StrEnum):
    OBLIGATION = "obligation"
    PROHIBITION = "prohibition"
    PERMISSION = "permission"
    SAFEGUARD = "safeguard"


class NormalizedRule(DomainModel):
    """Machine-checkable reading of a clause. It is an interpretation, not the clause text."""

    kind: RuleKind
    actor: str  # role id that bears the rule, or "any"
    action: str  # action id from the scenario's action catalogue, or a short verb phrase
    counterpart: str | None = None  # role id the action is directed at
    data_category: str | None = None
    condition: str | None = None
    deadline_minutes: int | None = Field(default=None, ge=0)


class PolicyClause(DomainModel):
    id: str = Field(pattern=CLAUSE_ID_PATTERN)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)  # verbatim from the extracted page (paraphrase if illustrative)
    source_file: str | None = None  # PDF filename in policies/sources/
    page: StrictInt | None = Field(
        default=None, ge=1
    )  # 1-based PDF page index, as in policies/extracted/
    article: str | None = None  # article/section number as printed, if any
    issuer: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    document_date: str = Field(pattern=DOCUMENT_DATE_PATTERN)
    status: ClauseStatus
    binding: StrictBool | Literal["unknown"]  # no "yes"/1 coercion
    normalized: NormalizedRule | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        if self.status is ClauseStatus.ILLUSTRATIVE:
            if self.binding is True:
                raise ValueError("an illustrative clause cannot be binding")
            if not self.notes:
                raise ValueError("an illustrative clause must explain in notes why it is needed")
        elif self.source_file is None or self.page is None:
            raise ValueError(f"a {self.status} clause must record source_file and page")
        if self.source_file is not None and not self.source_file.lower().endswith(".pdf"):
            raise ValueError("source_file must be a PDF filename")
        stripped = self.text.strip()
        if stripped.startswith(ELISION) or stripped.endswith(ELISION):
            raise ValueError("text must not start or end with an elision")
        return self
