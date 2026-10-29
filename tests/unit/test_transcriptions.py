"""Page-image transcriptions (human decision 2026-10-29): a clause flagged TRANSCRIBED_FLAG is
checked against policies/transcriptions/, never against the unreliable text layer, and an
unflagged clause never against a transcription."""

import json
from pathlib import Path

import pytest

from cascadeguard.domain.policies import TRANSCRIBED_FLAG, TRANSCRIBED_SOURCES, PolicyClause
from cascadeguard.knowledge.loader import (
    EXTRACTED_DIR,
    SOURCES_DIR,
    TRANSCRIPTIONS_DIR,
    load_clauses,
    quote_found_on_page,
)

CHARTER = "The UAE Charter for the Development and Use of Artificial Intelligence.pdf"
CLAUSE_ID = "uae.ai-charter.human-oversight"


def charter_clause():
    return next(c for c in load_clauses() if c.id == CLAUSE_ID)


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
    record = json.loads((TRANSCRIPTIONS_DIR / f"{stem}.jsonl").read_text("utf-8"))
    (tmp_path / f"{stem}.jsonl").write_text(json.dumps(record), encoding="utf-8")
    assert not quote_found_on_page(clause, extracted_dir=tmp_path)


def test_extracted_text_never_stands_in_for_a_transcription(tmp_path: Path) -> None:
    clause = charter_clause()
    stem = Path(CHARTER).stem
    record = json.loads((TRANSCRIPTIONS_DIR / f"{stem}.jsonl").read_text("utf-8"))
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
    for source in TRANSCRIBED_SOURCES:
        assert "unreliable" in rows[source], source
