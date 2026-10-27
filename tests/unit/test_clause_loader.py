import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from cascadeguard.domain.policies import ELISION, WEB_FLAG, ClauseStatus, PolicyClause
from cascadeguard.knowledge.loader import (
    ClauseLoadError,
    load_clauses,
    load_engine_clauses,
    quote_found_on_page,
    skipped_texts,
)

VALID: dict[str, Any] = {
    "id": "test.clause",
    "title": "A clause",
    "text": "Some verbatim text.",
    "source_file": "doc.pdf",
    "page": 3,
    "article": "Article (1)",
    "issuer": "Issuer",
    "jurisdiction": "UAE",
    "document_date": "2021",
    "status": "draft",
    "binding": True,
}

WEB_NOTE = f"{WEB_FLAG} (MANIFEST.md row 01)."

STATED: dict[str, Any] = {
    "basis": "stated",
    "kind": "obligation",
    "actor": "telecom_operator",
    "action": "report_to_telecom_regulator",
}
INTERPRETED: dict[str, Any] = {
    **STATED,
    "basis": "interpreted",
    "mapping_note": "The text names no actor; the operator is inferred.",
}


def write_clauses(directory: Path, *clauses: dict[str, Any]) -> None:
    (directory / "clauses.yaml").write_text(yaml.safe_dump({"clauses": list(clauses)}), "utf-8")


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    reviewed, sources = tmp_path / "reviewed", tmp_path / "sources"
    reviewed.mkdir()
    sources.mkdir()
    (sources / "doc.pdf").write_bytes(b"%PDF-")
    return reviewed, sources


def test_repository_clauses_load_with_unique_ids() -> None:
    clauses = load_clauses()
    assert clauses
    assert len({c.id for c in clauses}) == len(clauses)


def test_repository_clause_quotes_are_verbatim_on_their_cited_page() -> None:
    missing = [
        c.id
        for c in load_clauses()
        if c.status is not ClauseStatus.ILLUSTRATIVE and not quote_found_on_page(c)
    ]
    assert missing == []


# A gap may skip stray column, header or margin text only. Skipped text that could change the
# meaning of the quote (a qualifier, condition, modal, number or cross-reference) fails.
QUALIFIER = re.compile(
    r"\b(not|no|unless|except|only|provided that|subject to|without prejudice|"
    r"notwithstanding|may|shall|must|article|paragraph)\b|\d",
    re.IGNORECASE,
)
HARMLESS_GAP = re.compile(r"^(\d{1,2}|REQ-ML-[A-Z]+-\d{3})$")  # footnote marker, margin req id
MAX_GAP_CHARS = 200


def gap_problems(skipped: list[str]) -> list[str]:
    problems: list[str] = []
    for gap in (" ".join(s.split()) for s in skipped):
        if not gap:
            problems.append("empty gap")
        elif HARMLESS_GAP.match(gap):
            continue
        elif len(gap) > MAX_GAP_CHARS or QUALIFIER.search(gap):
            problems.append(gap)
    return problems


def test_repository_elisions_skip_only_harmless_text() -> None:
    problems: dict[str, list[str]] = {}
    for clause in load_clauses():
        if ELISION not in clause.text:
            continue
        skipped = skipped_texts(clause)
        assert skipped is not None, clause.id
        if found := gap_problems(skipped):
            problems[clause.id] = found
    assert problems == {}


@pytest.mark.parametrize(
    "gap",
    ["unless the patient consents", "within 72 hours", "subject to Article 5", "x" * 201, ""],
)
def test_gap_check_rejects_meaningful_skipped_text(gap: str) -> None:
    assert gap_problems([gap])


@pytest.mark.parametrize("gap", ["1", "REQ-ML-MNG-003", "c In the case that such explanations"])
def test_gap_check_allows_stray_markers_and_column_text(gap: str) -> None:
    assert gap_problems([gap]) == []


def test_engine_loads_only_reviewed_and_illustrative(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    write_clauses(
        reviewed,
        {**VALID, "id": "a.draft"},
        {**VALID, "id": "a.reviewed", "status": "reviewed"},
        {
            **VALID,
            "id": "a.illustrative",
            "status": "illustrative",
            "binding": False,
            "source_file": None,
            "page": None,
            "notes": "why it is needed",
        },
    )
    assert set(load_engine_clauses(reviewed, sources)) == {"a.reviewed", "a.illustrative"}


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"text": ""}, "empty text"),
        ({"status": "approved"}, "unknown status"),
        ({"binding": "maybe"}, "binding not true/false/unknown"),
        ({"binding": "yes"}, "binding coerced from a string"),
        ({"binding": 1}, "binding coerced from an int"),
        ({"page": "3"}, "page coerced from a string"),
        ({"page": None}, "draft without page"),
        ({"document_date": "March 2021"}, "unparseable date"),
        ({"source_file": "missing.pdf"}, "source file not in sources/"),
        ({"id": "Has Spaces"}, "bad id"),
        ({"extra_field": "x"}, "unknown field"),
        ({"status": "illustrative", "binding": True, "notes": "n"}, "illustrative but binding"),
        ({"status": "illustrative", "binding": False}, "illustrative without notes"),
        ({"source_file": "ocr/doc.ocr.pdf"}, "OCR source without the OCR flag"),
        ({"source_file": "web/page.pdf", "binding": False}, "web source without the web flag"),
        ({"source_file": "web/page.pdf", "notes": WEB_NOTE}, "web source marked binding"),
        ({"source_file": "./web/page.pdf", "binding": False}, "dotted web path, no flag"),
        ({"source_file": "WEB/page.pdf", "binding": False}, "upper-case web path, no flag"),
        ({"source_file": "./ocr/doc.ocr.pdf"}, "dotted OCR path, no flag"),
        ({"normalized": {k: v for k, v in STATED.items() if k != "basis"}}, "no basis"),
        ({"normalized": {**STATED, "basis": "assumed"}}, "unknown basis"),
        ({"normalized": {**STATED, "basis": "interpreted"}}, "interpreted, no mapping_note"),
        ({"normalized": {**INTERPRETED, "mapping_note": "  "}}, "interpreted, blank note"),
        ({"normalized": {**INTERPRETED, "mapping_note": "one\ntwo"}}, "multi-line note"),
    ],
)
def test_malformed_clause_rejects_whole_load(
    dirs: tuple[Path, Path], override: dict[str, Any], reason: str
) -> None:
    reviewed, sources = dirs
    write_clauses(reviewed, {**VALID, "id": "ok.clause"}, {**VALID, **override})
    with pytest.raises(ClauseLoadError):
        load_clauses(reviewed, sources)


def test_duplicate_clause_ids_are_rejected(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    write_clauses(reviewed, VALID, VALID)
    with pytest.raises(ClauseLoadError, match="duplicate"):
        load_clauses(reviewed, sources)


def test_invalid_yaml_is_rejected(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    (reviewed / "broken.yaml").write_text("clauses: [unclosed", "utf-8")
    with pytest.raises(ClauseLoadError):
        load_clauses(reviewed, sources)


def test_quote_check_honours_elisions_and_order(tmp_path: Path) -> None:
    page = {"source_file": "doc.pdf", "page": 3, "text": "Alpha beta\nNOISE gamma delta."}
    (tmp_path / "doc.jsonl").write_text(json.dumps(page) + "\n", "utf-8")
    clause = PolicyClause.model_validate({**VALID, "text": "Alpha beta [...] gamma delta."})
    assert quote_found_on_page(clause, tmp_path)
    reordered = clause.model_copy(update={"text": "gamma delta. [...] Alpha beta"})
    assert not quote_found_on_page(reordered, tmp_path)


@pytest.mark.parametrize(
    ("normalized", "label"),
    [(None, "draft"), (STATED, "draft"), (INTERPRETED, "draft (interpreted)")],
)
def test_normalized_basis_loads_and_shows_in_the_label(
    dirs: tuple[Path, Path], normalized: dict[str, Any] | None, label: str
) -> None:
    reviewed, sources = dirs
    clause = {**VALID} if normalized is None else {**VALID, "normalized": normalized}
    write_clauses(reviewed, clause)
    (loaded,) = load_clauses(reviewed, sources)
    assert loaded.status_label == label


def test_repository_interpreted_readings_have_a_mapping_note() -> None:
    for clause in load_clauses():
        if clause.normalized is not None and clause.normalized.basis == "interpreted":
            assert clause.normalized.mapping_note


def test_ocr_clause_with_flag_loads(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    (sources / "ocr").mkdir()
    (sources / "ocr" / "doc.ocr.pdf").write_bytes(b"%PDF-")
    clause = {**VALID, "source_file": "ocr/doc.ocr.pdf", "notes": "OCR — check against image."}
    write_clauses(reviewed, clause)
    (loaded,) = load_clauses(reviewed, sources)
    assert loaded.source_file == "ocr/doc.ocr.pdf"


def test_web_transcription_clause_loads_and_its_quote_is_checked(
    dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    reviewed, sources = dirs
    (sources / "web").mkdir()
    (sources / "web" / "page.pdf").write_bytes(b"%PDF-")
    clause = {
        **VALID,
        "source_file": "web/page.pdf",
        "binding": "unknown",
        "notes": WEB_NOTE,
    }
    write_clauses(reviewed, clause)
    (loaded,) = load_clauses(reviewed, sources)
    assert loaded.source_file == "web/page.pdf"
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    record = {"source_file": "web/page.pdf", "page": 3, "text": "x Some  verbatim\ntext. y"}
    (extracted / "page.jsonl").write_text(json.dumps({**record, "web": True}) + "\n", "utf-8")
    assert quote_found_on_page(loaded, extracted)
    assert not quote_found_on_page(loaded.model_copy(update={"page": 4}), extracted)


def test_repository_web_clauses_are_flagged_and_never_binding() -> None:
    web = [c for c in load_clauses() if (c.source_file or "").startswith("web/")]
    assert web
    for clause in web:
        assert WEB_FLAG in (clause.notes or ""), clause.id
        assert clause.binding is not True, clause.id
        assert clause.normalized is None, clause.id  # policy aims and principles: no duty read
        assert clause.status is ClauseStatus.DRAFT, clause.id


def test_quote_is_never_checked_against_another_document_with_the_same_stem(
    tmp_path: Path,
) -> None:
    """An original and a web copy named alike share an extracted name: the record must belong
    to the clause's own source_file."""
    page = {"source_file": "doc.pdf", "page": 3, "text": "Some verbatim text."}
    (tmp_path / "doc.jsonl").write_text(json.dumps(page) + "\n", "utf-8")
    original = PolicyClause.model_validate(VALID)
    assert quote_found_on_page(original, tmp_path)
    web = PolicyClause.model_validate(
        {**VALID, "source_file": "web/doc.pdf", "binding": False, "notes": WEB_NOTE}
    )
    assert not quote_found_on_page(web, tmp_path)
