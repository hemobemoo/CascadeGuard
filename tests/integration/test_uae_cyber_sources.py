"""Task 3 (human, 2026-11-06): the three UAE Cyber Security Council PDFs.

They are not redistributed (reproduction needs the CSC's prior written consent): the PDFs and
their extracted text are gitignored and pinned by SHA-256 (NOT_REDISTRIBUTED) and a per-page
text digest (policies/not_redistributed_pages.json). Their clauses are drafts in
policies/gap_examples_only/ (the NIST route): never loaded, never searched. Where the files are
present (the author's checkout) the quotes are checked on their pages; where they are absent (a
clone, CI) that check is skipped with the reason, and the committed digests still pin each
quoted page.
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from cascadeguard import cli
from cascadeguard.domain.policies import ClauseStatus
from cascadeguard.knowledge.kb import committed_index
from cascadeguard.knowledge.loader import (
    EXTRACTED_DIR,
    GAP_EXAMPLES_DIR,
    NOT_REDISTRIBUTED,
    REVIEWED_DIR,
    SOURCES_DIR,
    ClauseLoadError,
    gap_example_folder_clauses,
    load_clauses,
    load_engine_clauses,
    load_gap_example_clauses,
    page_digests,
    quote_found_on_page,
    skipped_texts,
    transcription_digest,
)
from cascadeguard.knowledge.retrieval import NOT_SEARCHED, extracted_digest, search_extracted

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "uae_health_access"
CSC_FILE = GAP_EXAMPLES_DIR / "uae_csc_cyber.yaml"
CSC_IDS = {
    "uae.csc-ai-policy.2-4-2-redundancy-failover",
    "uae.csc-ai-policy.3-4-3-redundant-systems-ready",
    "uae.csc-ai-policy.3-6-2-automated-response-human-intervention",
    "uae.csc-isf.cii-sectors-cross-sector-sharing",
    "uae.csc-isf.traffic-light-protocol",
    "uae.csc-cirp.ncrg-level3-declaration",
    "uae.csc-cirp.ncrg-sector-impact-information",
}
# (PDF page, printed page) of each draft, as the human asked them recorded.
PAGES = {
    "uae.csc-ai-policy.2-4-2-redundancy-failover": (15, 14),
    "uae.csc-ai-policy.3-4-3-redundant-systems-ready": (36, 35),
    "uae.csc-ai-policy.3-6-2-automated-response-human-intervention": (41, 40),
    "uae.csc-isf.cii-sectors-cross-sector-sharing": (32, 31),
    "uae.csc-isf.traffic-light-protocol": (24, 23),
    "uae.csc-cirp.ncrg-level3-declaration": (18, 17),
    "uae.csc-cirp.ncrg-sector-impact-information": (16, 15),
}
SCOPE = "applies to federal entities and CII entities"
# Gate 1 (scoped), human 2026-11-06: reviewed as gap examples only. The two NCRG clauses stay
# drafts: they map to no failure (the Level 3 declaration; the sector-impact entry was dropped
# at gate 7).
REVIEWED = CSC_IDS - {
    "uae.csc-cirp.ncrg-level3-declaration",
    "uae.csc-cirp.ncrg-sector-impact-information",
}
LEGAL = {
    "National Cyber Security Policy for Artificial Intelligence v1.1.pdf": (
        "Council-approved national policy (as printed on its cover); legal force for this "
        "scenario not established."
    ),
    "Cyber Security Information Sharing Framework V2.0.pdf": (
        "Cabinet-approved national framework (as printed on its cover); legal force for this "
        "scenario not established."
    ),
    "Cyber Incident Response Plan V2.0.pdf": (
        "Cabinet-approved national plan (as printed on its cover); legal force for this "
        "scenario not established."
    ),
}


def csc_clauses() -> list[Any]:
    return [c for c in gap_example_folder_clauses() if c.source_file in NOT_REDISTRIBUTED]


def present(name: str) -> bool:
    return (SOURCES_DIR / name).exists() and (EXTRACTED_DIR / f"{Path(name).stem}.jsonl").exists()


# --- Not redistributed -----------------------------------------------------------------------


def test_the_pdfs_and_their_extracted_text_are_never_committed() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    tracked = subprocess.run(
        ["git", "ls-files", "policies/sources", "policies/extracted"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for name in NOT_REDISTRIBUTED:
        stem = Path(name).stem
        assert f"policies/sources/{name}" in ignore and f"policies/extracted/{stem}.jsonl" in ignore
        assert not any(stem in t for t in tracked), name


def test_the_hashes_are_in_the_inventory_and_match_where_the_files_are_present() -> None:
    inventory = (ROOT / "docs" / "policy-inventory.md").read_text(encoding="utf-8")
    for name, digest in NOT_REDISTRIBUTED.items():
        assert f"| `{name}` | `{digest}` |" in inventory, name
        if (SOURCES_DIR / name).exists():
            assert hashlib.sha256((SOURCES_DIR / name).read_bytes()).hexdigest() == digest, name


def test_every_page_digest_matches_the_extracted_text_where_present() -> None:
    digests = page_digests()
    assert set(digests) == set(NOT_REDISTRIBUTED)
    checked = 0
    for name, pages in digests.items():
        jsonl = EXTRACTED_DIR / f"{Path(name).stem}.jsonl"
        if not jsonl.exists():
            continue  # a clone or CI: the text is not redistributed
        records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        assert {r["page"]: transcription_digest(r["text"]) for r in records} == pages, name
        checked += 1
    if not checked:
        pytest.skip("source text not present (not redistributed): digests checked by the author")


def test_each_draft_quote_is_verbatim_on_its_page_where_the_text_is_present() -> None:
    """Locally: every quote on its cited page, elisions skipping only a bullet glyph. Without
    the text (a clone, CI) the quote check is skipped, and each cited page must have a committed
    digest, so the page checked is pinned."""
    digests = page_digests()
    clauses = csc_clauses()
    assert {c.id for c in clauses} == CSC_IDS
    for c in clauses:
        assert c.source_file is not None and c.page is not None
        assert str(c.page) in {str(p) for p in digests[c.source_file]}, c.id
    local = [c for c in clauses if c.source_file is not None and present(c.source_file)]
    for c in local:
        assert quote_found_on_page(c), c.id
        assert all(gap == "•" for gap in (skipped_texts(c) or [])), c.id
    if not local:
        pytest.skip("source text not present (not redistributed): quotes checked by the author")


def test_a_missing_source_is_accepted_only_when_listed(tmp_path: Path) -> None:
    folder, sources = tmp_path / "clauses", tmp_path / "sources"
    folder.mkdir()
    sources.mkdir()
    data = yaml.safe_load(CSC_FILE.read_text(encoding="utf-8"))
    (folder / "csc.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert {c.id for c in load_clauses(folder, sources)} == CSC_IDS  # no PDF on disk
    data["clauses"][0]["source_file"] = "Some Other Unlisted Document.pdf"
    (folder / "csc.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ClauseLoadError, match="unknown source_file"):
        load_clauses(folder, sources)


def test_they_are_never_searched_and_the_search_digest_ignores_their_text(
    tmp_path: Path,
) -> None:
    assert set(NOT_REDISTRIBUTED) <= NOT_SEARCHED
    without = tmp_path / "extracted"
    shutil.copytree(EXTRACTED_DIR, without)
    for name in NOT_REDISTRIBUTED:
        (without / f"{Path(name).stem}.jsonl").unlink(missing_ok=True)
    assert extracted_digest(without) == extracted_digest()
    for chunk in committed_index().chunks:
        assert chunk.source_file not in NOT_REDISTRIBUTED
    # Their own wording, searched: never one of their pages (where the text is present).
    for query in (
        "cross-sector cybersecurity information sharing",
        "Traffic Light Protocol",
        "redundancy and failover mechanisms",
        "Significant Cyber Incident Level 3",
    ):
        assert all(
            s.source_file not in NOT_REDISTRIBUTED for s in search_extracted(query, limit=1000)
        )


# --- The drafts ---------------------------------------------------------------------------------


def test_the_clauses_carry_the_labels_the_human_set() -> None:
    for c in csc_clauses():
        status = ClauseStatus.REVIEWED if c.id in REVIEWED else ClauseStatus.DRAFT
        assert c.status is status and c.binding == "unknown", c.id
        assert c.issuer == "UAE Cyber Security Council" and c.jurisdiction.startswith("UAE")
        assert c.status_label == f"{status} · binding unknown", c.id
        notes = " ".join((c.notes or "").split())
        assert f"Legal status: {LEGAL[cast(str, c.source_file)]}" in notes, c.id
        pdf, printed = PAGES[c.id]
        assert c.page == pdf and f"Viewer page {pdf} is printed page {printed}." in c.notes
        assert SCOPE in c.notes and "not designated CII" in c.notes, c.id
        assert "Version as printed:" in c.notes and c.normalized is None, c.id
    dates = {c.source_file: c.document_date for c in csc_clauses()}
    assert dates == {
        "National Cyber Security Policy for Artificial Intelligence v1.1.pdf": "2025-11",
        "Cyber Security Information Sharing Framework V2.0.pdf": "2023-05",
        "Cyber Incident Response Plan V2.0.pdf": "2023-05",
    }


def test_shall_and_should_are_as_printed() -> None:
    by_id = {c.id: c for c in csc_clauses()}
    assert "shall" in by_id["uae.csc-ai-policy.2-4-2-redundancy-failover"].text
    for cid in (
        "uae.csc-ai-policy.3-4-3-redundant-systems-ready",
        "uae.csc-ai-policy.3-6-2-automated-response-human-intervention",
    ):
        assert "should" in by_id[cid].text and "shall" not in by_id[cid].text, cid
    for c in by_id.values():  # the title keeps the text's own modal verb
        for modal in ("shall", "should"):
            if modal in c.title:
                assert modal in c.text, c.id


def test_they_are_not_loaded_into_the_simulation() -> None:
    assert not CSC_IDS & {c.id for c in load_clauses()}
    assert not CSC_IDS & set(load_engine_clauses())
    # The reviewed ones are shown only by the report builder, as gap examples; drafts never.
    assert CSC_IDS & set(load_gap_example_clauses()) == REVIEWED
    world = cli.load_world(SCENARIO)
    baseline = world.baseline()
    for view in baseline.views:
        assert not CSC_IDS & {c.id for c in view.role_clauses}, view.role_id


def test_loading_them_would_leave_the_diagnosis_goals_and_ranking_unchanged(
    tmp_path: Path,
) -> None:
    """What would change if the human loaded them (the brief): a temporary clause directory with
    the reviewed corpus plus the drafts set to reviewed. Only the analysts' views may change."""
    target = tmp_path / "reviewed"
    shutil.copytree(REVIEWED_DIR, target)
    data = yaml.safe_load(CSC_FILE.read_text(encoding="utf-8"))
    data["clauses"] = [{**c, "status": "reviewed"} for c in data["clauses"]]
    (target / "uae_csc_cyber.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    base = cli.run_scenario(SCENARIO)
    loaded = cli.run_scenario(SCENARIO, target)
    assert {cid for cid, _ in loaded.loaded_clauses} >= CSC_IDS
    assert not CSC_IDS & {cid for cid, _ in base.loaded_clauses}

    # A temporary directory is labelled "SYNTHETIC FIXTURES from ..." in each qualification;
    # with that label put back, every failure is the same.
    def relabel(f: Any) -> Any:
        return f.model_copy(
            update={"qualification": f.qualification.replace(loaded.clause_set, base.clause_set)}
        )

    assert [relabel(f) for f in loaded.failures] == list(base.failures)
    assert [relabel(f) for f in loaded.causes] == list(base.causes)
    assert loaded.goals == base.goals and loaded.findings == base.findings
    ranked = [c.proposal.repair_id for c in cli.search_repairs(SCENARIO, target).ranked]
    assert ranked == [c.proposal.repair_id for c in cli.search_repairs(SCENARIO).ranked]
