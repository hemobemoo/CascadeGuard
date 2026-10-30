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
    ClauseLoadError,
    load_clauses,
    load_transcription_approvals,
    quote_found_on_page,
    reviewed_transcriptions,
    transcription_digest,
)
from cascadeguard.knowledge.retrieval import extracted_digest, search_extracted

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


def test_transcription_pages_are_unique() -> None:
    keys = [(r["source_file"], r["page"]) for r in all_records()]
    assert len(keys) == len(set(keys))


def test_a_duplicated_page_is_refused_by_the_quote_check_and_the_search(tmp_path: Path) -> None:
    """An unchecked record placed before the approved one must not shadow it (test-breaker,
    2026-10-29)."""
    clause = charter_clause()
    stem = Path(CHARTER).stem
    approved = page_record(stem, clause.page)
    forged = approved | {"text": "FORGED UNCHECKED TEXT. " + str(approved["text"])}
    rows = "".join(json.dumps(r) + "\n" for r in (forged, approved))
    (tmp_path / f"{stem}.jsonl").write_text(rows, encoding="utf-8")
    with pytest.raises(ClauseLoadError, match="records for page"):
        quote_found_on_page(clause, transcriptions_dir=tmp_path)
    with pytest.raises(ClauseLoadError, match="two records"):
        search_extracted("forged", transcriptions_dir=tmp_path)


@pytest.mark.parametrize("page", [4, "4", " 04", 4.0, True])
@pytest.mark.parametrize("where", ["before", "after", "other file"])
def test_a_second_record_for_a_page_is_refused_however_it_is_spelled(
    tmp_path: Path, page: object, where: str
) -> None:
    """test-breaker round 4 (2026-10-30): a page spelled "4" or " 04" passed the duplicate check
    in the search. Every spelling, in either position or another file, is refused."""
    clause = charter_clause()
    stem = Path(CHARTER).stem
    approved = page_record(stem, clause.page)
    # True poses as page 1 (True == 1); the others as page 4.
    fake = approved | {"page": page, "text": "zzforgedword " + str(approved["text"])}
    if where == "other file":
        (tmp_path / f"{stem}.jsonl").write_text(json.dumps(approved) + "\n", encoding="utf-8")
        (tmp_path / "zz.jsonl").write_text(json.dumps(fake) + "\n", encoding="utf-8")
    else:
        rows = (fake, approved) if where == "before" else (approved, fake)
        text = "".join(json.dumps(r) + "\n" for r in rows)
        (tmp_path / f"{stem}.jsonl").write_text(text, encoding="utf-8")
    with pytest.raises(ClauseLoadError):
        search_extracted("zzforgedword", transcriptions_dir=tmp_path)
    with pytest.raises(ClauseLoadError):
        extracted_digest.__wrapped__(EXTRACTED_DIR, tmp_path)
    if where != "other file":  # the quote check reads only the clause's own file
        with pytest.raises(ClauseLoadError):
            quote_found_on_page(clause, transcriptions_dir=tmp_path)


def test_every_transcription_page_is_a_plain_int() -> None:
    assert all(type(r["page"]) is int and isinstance(r["source_file"], str) for r in all_records())


def unpinned_or_edited(tmp_path: Path, how: str) -> Path:
    """A copy of the committed Charter transcriptions where reviewed page 4 was edited after
    approval, lost its pin, or is pinned to another page's digest. Returns the approvals file."""
    stem = Path(CHARTER).stem
    rows = [page_record(stem, p) for p in (1, 2, 3, 4, 5)]
    approvals = load_transcription_approvals()
    if how == "edited":
        rows[3] = rows[3] | {"text": str(rows[3]["text"]) + " zzeditedword"}
    elif how == "unpinned":
        del approvals[f"{CHARTER}#4"]
    else:
        approvals[f"{CHARTER}#4"] = approvals[f"{CHARTER}#3"]
    text = "".join(json.dumps(r) + "\n" for r in rows)
    (tmp_path / f"{stem}.jsonl").write_text(text, encoding="utf-8")
    data: dict[str, object] = {
        "approved": {},
        "reapproval_needed": [],
        "approved_transcriptions": approvals,
    }
    path = tmp_path / "approvals.yaml"
    path.write_text(json.dumps(data), encoding="utf-8")  # JSON is valid YAML
    return path


@pytest.mark.parametrize("how", ["edited", "unpinned", "pinned to another page"])
def test_a_reviewed_page_that_does_not_match_its_pin_is_refused_at_runtime(
    tmp_path: Path, how: str
) -> None:
    """test-breaker round 5 (deferred MINOR, fixed in PR 3): the search served any int page that
    said "reviewed" without checking approved_transcriptions at runtime. The shared reader now
    refuses it, for the search and its digest alike; the vector index uses the same reader."""
    approvals = unpinned_or_edited(tmp_path, how)
    with pytest.raises(ClauseLoadError, match="does not match its approval"):
        search_extracted("zzeditedword", transcriptions_dir=tmp_path, approvals_file=approvals)
    with pytest.raises(ClauseLoadError, match="does not match its approval"):
        extracted_digest.__wrapped__(EXTRACTED_DIR, tmp_path, approvals)


def test_the_committed_transcriptions_pass_the_runtime_pin_check() -> None:
    assert [r["page"] for r in reviewed_transcriptions()] == [1, 2, 3, 4, 5]
