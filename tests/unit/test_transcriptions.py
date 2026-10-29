"""Page-image transcriptions (human decision 2026-10-29): a clause flagged TRANSCRIBED_FLAG is
checked against policies/transcriptions/, never against the unreliable text layer, and an
unflagged clause never against a transcription."""

import json
from pathlib import Path

import pytest

from cascadeguard.domain.policies import (
    TRANSCRIBED_FLAG,
    TRANSCRIBED_SOURCES,
    ClauseStatus,
    PolicyClause,
)
from cascadeguard.knowledge.loader import (
    EXTRACTED_DIR,
    SOURCES_DIR,
    TRANSCRIPTIONS_DIR,
    load_clauses,
    load_transcription_approvals,
    quote_found_on_page,
    transcription_digest,
)

CHARTER = "The UAE Charter for the Development and Use of Artificial Intelligence.pdf"
CLAUSE_ID = "uae.ai-charter.human-oversight"


def charter_clause():
    return next(c for c in load_clauses() if c.id == CLAUSE_ID)


def page_record(stem: str, page: int | None) -> dict[str, object]:
    lines = (TRANSCRIPTIONS_DIR / f"{stem}.jsonl").read_text("utf-8").splitlines()
    return next(r for r in map(json.loads, lines) if r["page"] == page)


def test_the_charter_quote_is_found_only_in_the_transcription() -> None:
    clause = charter_clause()
    assert clause.source_file == CHARTER and TRANSCRIBED_FLAG in (clause.notes or "")
    assert quote_found_on_page(clause)
    # The text layer is garbled here ("human over / oversight Al"): the quote is not on it.
    unflagged = clause.model_copy(update={"notes": "no flag"})
    assert not quote_found_on_page(unflagged)


def test_a_transcription_never_stands_in_for_extracted_text(tmp_path: Path) -> None:
    clause = charter_clause().model_copy(update={"notes": "no flag"})
    stem = Path(CHARTER).stem
    record = page_record(stem, clause.page)
    (tmp_path / f"{stem}.jsonl").write_text(json.dumps(record), encoding="utf-8")
    assert not quote_found_on_page(clause, extracted_dir=tmp_path)


def test_extracted_text_never_stands_in_for_a_transcription(tmp_path: Path) -> None:
    clause = charter_clause()
    stem = Path(CHARTER).stem
    record = page_record(stem, clause.page)
    del record["transcribed"]  # an extracted-style record in the transcriptions folder
    (tmp_path / f"{stem}.jsonl").write_text(json.dumps(record), encoding="utf-8")
    assert not quote_found_on_page(clause, transcriptions_dir=tmp_path)


def test_every_transcription_names_a_real_page_of_a_committed_original() -> None:
    inventory = json.loads((EXTRACTED_DIR / "_inventory.json").read_text("utf-8"))
    pages = {e["source_file"]: e["page_count"] for e in inventory}
    files = sorted(TRANSCRIPTIONS_DIR.glob("*"))
    assert [f.suffix for f in files] == [".jsonl"] * len(files)
    for path in files:
        for line in path.read_text("utf-8").splitlines():
            record = json.loads(line)
            source = record["source_file"]
            assert path.stem == Path(source).stem
            assert source in TRANSCRIBED_SOURCES and (SOURCES_DIR / source).is_file()
            assert 1 <= record["page"] <= pages[source]
            assert record["transcribed"] is True and record["transcribed_from"] == "page image"
            # Draft until the human checks it against the image; set to reviewed in the same
            # "Reviewed by human" commit as the clause that rests on it.
            assert record["status"] in ("draft", "reviewed")


def test_only_sources_with_an_unreliable_text_layer_may_be_transcribed() -> None:
    """A transcription could otherwise stand in for any page (test-breaker, 2026-10-29)."""
    data = charter_clause().model_dump()
    with pytest.raises(ValueError, match="TRANSCRIBED_SOURCES"):
        PolicyClause.model_validate(data | {"source_file": "doc.pdf"})
    inventory = (Path(__file__).resolve().parents[2] / "docs" / "policy-inventory.md").read_text(
        "utf-8"
    )
    rows = {
        line.split("|")[2].strip(" `"): line for line in inventory.splitlines() if "| `" in line
    }
    for source in TRANSCRIBED_SOURCES:  # the row's last column ("Clean?") says so
        clean = rows[source].rstrip(" |").rsplit("|", 1)[1]
        assert "No — " in clean and "unreliable" in clean and "not unreliable" not in clean


def all_records() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for path in sorted(TRANSCRIPTIONS_DIR.glob("*.jsonl"))
        for line in path.read_text("utf-8").splitlines()
        if line
    ]


def test_every_reviewed_transcription_matches_its_approved_digest() -> None:
    """AGENTS.md transcription route: a reviewed page is pinned like a reviewed clause, so an
    edit after the human's check is caught (phase-auditor, 2026-10-29)."""
    approved = load_transcription_approvals()
    reviewed = {
        f"{r['source_file']}#{r['page']}": r for r in all_records() if r["status"] == "reviewed"
    }
    assert set(reviewed) <= set(approved), "reviewed without a human approval"
    for key, record in reviewed.items():
        assert record.get("reviewed_by") and record.get("reviewed_on"), key
        assert transcription_digest(str(record["text"])) == approved[key], (
            f"{key} was edited after approval: set it back to draft"
        )


def test_a_reviewed_clause_rests_only_on_a_reviewed_transcription() -> None:
    status = {(r["source_file"], r["page"]): r["status"] for r in all_records()}
    flagged = [c for c in load_clauses() if TRANSCRIBED_FLAG in (c.notes or "")]
    assert flagged
    for c in flagged:
        if c.status is ClauseStatus.REVIEWED:
            assert status[(c.source_file, c.page)] == "reviewed", c.id
