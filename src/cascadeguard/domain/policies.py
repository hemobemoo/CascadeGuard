"""Policy clauses extracted from the PDFs in policies/sources/ (see AGENTS.md)."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from cascadeguard.domain.base import DomainModel

ELISION = "[...]"  # marks an omission inside a verbatim quote
OCR_DIR = "ocr/"  # source_file prefix of OCR'd copies in policies/sources/ocr/ (derived sources)
OCR_FLAG = "OCR — check against image"  # must appear in notes of a clause quoted from OCR text
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


class NormalizedBasis(StrEnum):
    # The text names the actor and the duty or permission; only role names are mapped
    # (e.g. Licensees -> telecom_operator).
    STATED = "stated"
    # The actor or action is inferred; mapping_note gives a one-line justification.
    INTERPRETED = "interpreted"


class NormalizedRule(DomainModel):
    """Machine-checkable reading of a clause. It is an interpretation, not the clause text.

    The engine treats both bases the same; reports and the UI show "interpreted" next to the
    clause's status label (PolicyClause.status_label).
    """

    basis: NormalizedBasis
    mapping_note: str | None = None  # required when basis is interpreted; one line
    kind: RuleKind
    actor: str  # role id that bears the rule, or "any"
    action: str  # action id from the scenario's action catalogue, or a short verb phrase
    counterpart: str | None = None  # role id the action is directed at
    data_category: str | None = None
    condition: str | None = None
    deadline_minutes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_basis(self) -> Self:
        note = (self.mapping_note or "").strip()
        if self.basis is NormalizedBasis.INTERPRETED and not note:
            raise ValueError("an interpreted normalized reading needs a mapping_note")
        if "\n" in note:
            raise ValueError("mapping_note must be one line")
        return self


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
        if (self.source_file or "").startswith(OCR_DIR) and OCR_FLAG not in (self.notes or ""):
            raise ValueError(f"a clause quoted from an OCR'd copy must say {OCR_FLAG!r} in notes")
        stripped = self.text.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        if stripped.startswith(ELISION) or stripped.endswith(ELISION):
            raise ValueError("text must not start or end with an elision")
        return self

    @property
    def status_label(self) -> str:
        """The label reports and the UI show next to the clause, e.g. "draft (interpreted)"."""
        if self.normalized is not None and self.normalized.basis is NormalizedBasis.INTERPRETED:
            return f"{self.status} (interpreted)"
        return str(self.status)
