"""Policy clauses extracted from the PDFs in policies/sources/ (see AGENTS.md)."""

from datetime import date
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from cascadeguard.domain.base import DomainModel

ELISION = "[...]"  # marks an omission inside a verbatim quote
OCR_DIR = "ocr/"  # source_file prefix of OCR'd copies in policies/sources/ocr/ (derived sources)
OCR_FLAG = "OCR — check against image"  # must appear in notes of a clause quoted from OCR text
WEB_DIR = "web/"  # source_file prefix of web-page transcriptions in policies/sources/web/
WEB_FLAG = "web transcription — unverified"  # must appear in notes of a clause quoted from one
LABEL_SEPARATOR = " · "  # between a clause's status and its qualifiers in status_label
# Originals in policies/sources/ that are not official documents, with the type shown in their
# clauses' labels. Each must match its row in docs/policy-inventory.md (tested).
SOURCE_TYPES = {"UAE Policy Foundation.pdf": "unofficial compilation"}
# English texts of UAE legislation whose Arabic text is authoritative and whose English version
# is not verified as an official translation (human decision 2026-10-29). Each is listed under
# "English translations not verified as official" in docs/policy-inventory.md (tested).
TRANSLATIONS = frozenset(
    {
        "887026278-TDRA-Telecom-Law-Final-English-o.pdf",
        "ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf",
        "Dubai Law No. (26) of 2015.pdf",
        "Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf",
        "UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf",
    }
)
# A non-UAE jurisdiction that starts with this is an intergovernmental instrument (OECD, UNESCO,
# ITU): "international precedent". Any other non-UAE one is a single jurisdiction (EU, US):
# "foreign precedent" (human decision 2026-10-29).
INTERNATIONAL = "International"
# A jurisdiction whose first words are one of these is a UAE source; any other is an
# international one. Whole words only: "UAEU partner states" is not the UAE.
UAE_JURISDICTIONS = (
    "UAE",
    "United Arab Emirates",
    "Abu Dhabi",
    "Dubai",
    "Sharjah",
    "Ajman",
    "Umm Al Quwain",
    "Ras Al Khaimah",
    "Fujairah",
)


def is_international_jurisdiction(jurisdiction: str) -> bool:
    """Does the jurisdiction start with INTERNATIONAL as a whole word, in any case?"""
    word = jurisdiction.split(maxsplit=1)[0] if jurisdiction.strip() else ""
    return word.casefold() == INTERNATIONAL.casefold()


def _plain_name(source_file: str) -> str:
    """The source path without "." parts, case-folded (as in_source_dir)."""
    return "/".join(p for p in source_file.split("/") if p not in ("", ".")).casefold()


def _source_type(source_file: str | None) -> str | None:
    """The SOURCE_TYPES entry for this file, ignoring "." parts and case."""
    if source_file is None:
        return None
    name = _plain_name(source_file)
    return next((t for f, t in SOURCE_TYPES.items() if f.casefold() == name), None)


def is_translation(source_file: str | None) -> bool:
    """Is this file listed in TRANSLATIONS, ignoring "." parts and case?"""
    return source_file is not None and _plain_name(source_file) in {
        f.casefold() for f in TRANSLATIONS
    }


def is_uae_jurisdiction(jurisdiction: str) -> bool:
    """Does the jurisdiction start with the UAE or one of its emirates, as whole words?"""
    return any(
        jurisdiction == name or jurisdiction.startswith((f"{name} ", f"{name},", f"{name};"))
        for name in UAE_JURISDICTIONS
    )


CLAUSE_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
# Year, year-month, full ISO date, or "unknown" when the PDF prints no date (never guessed).
DOCUMENT_DATE_PATTERN = r"^(\d{4}(-\d{2}(-\d{2})?)?|unknown)$"


def in_source_dir(source_file: str | None, directory: str) -> bool:
    """Does a plain source path lie in this sources subdirectory ("ocr/", "web/")? Ignores "."
    parts and case (Windows and macOS file systems ignore case). A path with ".." or a backslash
    is left to the loader, which refuses it for its path."""
    if source_file is None or "\\" in source_file:
        return False
    parts = [p for p in source_file.split("/") if p not in ("", ".")]
    return len(parts) > 1 and ".." not in parts and parts[0].casefold() == directory.strip("/")


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
        if self.document_date != "unknown":
            year, *rest = (int(p) for p in self.document_date.split("-"))
            try:  # a real calendar date, not just the right shape ("2020-13-45" is refused)
                date(year, *[*rest, 1, 1][:2])
            except ValueError as exc:
                raise ValueError(f"document_date {self.document_date!r}: {exc}") from exc
        if self.status is ClauseStatus.ILLUSTRATIVE:
            if self.binding is True:
                raise ValueError("an illustrative clause cannot be binding")
            if not self.notes:
                raise ValueError("an illustrative clause must explain in notes why it is needed")
            if self.source_file is not None or self.page is not None:  # human decision 2026-10-28
                raise ValueError(
                    "an illustrative clause is not quoted from a source: no source_file"
                )
        elif self.source_file is None or self.page is None:
            raise ValueError(f"a {self.status} clause must record source_file and page")
        if self.source_file is not None and not self.source_file.lower().endswith(".pdf"):
            raise ValueError("source_file must be a PDF filename")
        if in_source_dir(self.source_file, OCR_DIR) and OCR_FLAG not in (self.notes or ""):
            raise ValueError(f"a clause quoted from an OCR'd copy must say {OCR_FLAG!r} in notes")
        if in_source_dir(self.source_file, WEB_DIR):
            if WEB_FLAG not in (self.notes or ""):
                raise ValueError(f"a clause quoted from a web transcription must say {WEB_FLAG!r}")
            if self.binding is True:  # an unverified transcription is never shown as binding text
                raise ValueError("a clause quoted from a web transcription cannot be binding")
        stripped = self.text.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        if stripped.startswith(ELISION) or stripped.endswith(ELISION):
            raise ValueError("text must not start or end with an elision")
        return self

    @property
    def status_label(self) -> str:
        """The label agents, reports and the UI show next to the clause, e.g.
        "reviewed · not binding · foreign precedent" (human decisions 2026-10-29): the status,
        then for a sourced clause its binding status and, where it is not an official UAE source,
        its source type. An illustrative clause keeps its plain label."""
        label = str(self.status)
        if self.normalized is not None and self.normalized.basis is NormalizedBasis.INTERPRETED:
            label += " (interpreted)"
        if self.status is ClauseStatus.ILLUSTRATIVE:
            return label
        return LABEL_SEPARATOR.join((label, *self.qualifiers))

    @property
    def qualifiers(self) -> tuple[str, ...]:
        """Binding status; then the source type when the source is not an original document
        (web transcription, OCR copy, or a type recorded in SOURCE_TYPES); then "English
        translation" for a file in TRANSLATIONS; then, when the jurisdiction does not start with
        the UAE or one of its emirates, "international precedent" for an intergovernmental
        instrument or "foreign precedent" for another country or the EU. Empty for an
        illustrative clause."""
        if self.status is ClauseStatus.ILLUSTRATIVE:
            return ()
        binding = {True: "binding", False: "not binding", "unknown": "binding unknown"}
        parts = [binding[self.binding]]
        if in_source_dir(self.source_file, WEB_DIR):
            parts.append("web transcription")
        elif in_source_dir(self.source_file, OCR_DIR):
            parts.append("OCR copy")
        elif (kind := _source_type(self.source_file)) is not None:
            parts.append(kind)
        if is_translation(self.source_file):
            parts.append("English translation")
        if not is_uae_jurisdiction(self.jurisdiction):
            international = is_international_jurisdiction(self.jurisdiction)
            parts.append("international precedent" if international else "foreign precedent")
        return tuple(parts)
