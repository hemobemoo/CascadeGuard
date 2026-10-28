"""Web transcriptions in policies/sources/web/: the manifest table and the extracted records."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "policies" / "sources" / "web"
EXTRACTED = ROOT / "policies" / "extracted"
HEADER = (
    "| File | URL | Retrieved | Issuer | Date | Type | Status |\n|---|---|---|---|---|---|---|\n"
)
REST = "2026-10-27 | Issuer | 2024 | policy | unverified"


def row(name: str, url: str, rest: str = REST) -> str:
    return f"| `{name}` | {url} | {rest} |"


def extract_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "extract_pdf_text", ROOT / "scripts" / "extract_pdf_text.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_manifest(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "MANIFEST.md"
    path.write_text("# Manifest\n\n" + HEADER + "".join(r + "\n" for r in rows), "utf-8")
    return path


def test_manifest_rows_give_each_pdf_its_url(tmp_path: Path) -> None:
    script = extract_script()
    manifest = write_manifest(
        tmp_path,
        row("a.pdf", "https://example.org/a"),
        row(
            "b.pdf",
            "https://example.org/b?x=1",
            "2026-10-27 | OECD | 2024 | international precedent | unverified",
        ),
    )
    urls = script.manifest_urls(manifest, ["a.pdf", "b.pdf"])
    assert urls == {"a.pdf": "https://example.org/a", "b.pdf": "https://example.org/b?x=1"}


A = "https://e.org/a"


@pytest.mark.parametrize(
    ("rows", "pdfs", "reason"),
    [
        ([row("a.pdf", A)], ["a.pdf", "b.pdf"], "no row"),
        ([row("a.pdf", A), row("c.pdf", "https://e.org/c")], ["a.pdf"], "rows for files"),
        ([row("a.pdf", A), row("a.pdf", "https://e.org/b")], ["a.pdf"], "two rows"),
        ([row("a.pdf", "http://e.org/a")], ["a.pdf"], "https"),
        ([row("a.pdf", "")], ["a.pdf"], "https"),
        ([row("a.pdf", f"{A} https://e.org/b")], ["a.pdf"], "https"),
        ([row("a.pdf", "https://")], ["a.pdf"], "https"),
        ([row("a.pdf", A), "  " + row("a.pdf", "https://e.org/b")], ["a.pdf"], "malformed"),
        ([row("a.pdf", A), row("a.pdf", A).replace("`", "")], ["a.pdf"], "malformed"),
        (
            [row("a.pdf", A, "2026-13-45 | Issuer | 2024 | policy | unverified")],
            ["a.pdf"],
            "retrieval",
        ),
        ([row("a.pdf", A, "2026-10-27 | Issuer | 2024 | policy")], ["a.pdf"], "columns"),
        (
            [row("a.pdf", A, "27 Oct 2026 | Issuer | 2024 | policy | unverified")],
            ["a.pdf"],
            "retrieval",
        ),
        ([row("a.pdf", A, "2026-10-27 |  | 2024 | policy | unverified")], ["a.pdf"], "issuer"),
        ([row("a.pdf", A, "2026-10-27 | Issuer |  | policy | unverified")], ["a.pdf"], "date"),
        (
            [row("a.pdf", A, "2026-10-27 | Issuer | 2024 | guidance | unverified")],
            ["a.pdf"],
            "type",
        ),
        ([row("a.pdf", A, "2026-10-27 | Issuer | 2024 | law | reviewed")], ["a.pdf"], "unverified"),
        (
            [row("a.pdf", A, "2026-10-27 | Issuer | 2024 | law | superseded")],
            ["a.pdf"],
            "unverified",
        ),
    ],
)
def test_malformed_manifest_stops_the_extraction(
    tmp_path: Path, rows: list[str], pdfs: list[str], reason: str
) -> None:
    script = extract_script()
    with pytest.raises(script.ManifestError, match=reason):
        script.manifest_urls(write_manifest(tmp_path, *rows), pdfs)


def test_repository_manifest_lists_every_web_pdf() -> None:
    pdfs = sorted(p.name for p in WEB.glob("*.pdf"))
    assert len(pdfs) == 7
    urls = extract_script().manifest_urls(WEB / "MANIFEST.md", pdfs)
    assert sorted(urls) == pdfs


def test_every_web_pdf_is_extracted_with_its_url_and_marked_web() -> None:
    urls = extract_script().manifest_urls(WEB / "MANIFEST.md", [p.name for p in WEB.glob("*.pdf")])
    inventory = {
        e["source_file"]: e for e in json.loads((EXTRACTED / "_inventory.json").read_text("utf-8"))
    }
    for name, url in urls.items():
        entry = inventory[f"web/{name}"]
        assert (entry["web"], entry["source_url"], entry["manifest"]) == (
            True,
            url,
            "web/MANIFEST.md",
        )
        lines = (EXTRACTED / f"{Path(name).stem}.jsonl").read_text("utf-8").splitlines()
        assert len(lines) == entry["page_count"] > 0
        for line in lines:
            record = json.loads(line)
            assert (record["source_file"], record["web"], record["source_url"]) == (
                f"web/{name}",
                True,
                url,
            )
    # Originals and OCR copies are not marked web.
    assert all("web" not in e for k, e in inventory.items() if not k.startswith("web/"))


def test_web_pdfs_are_byte_identical_to_the_hashes_recorded_at_placement() -> None:
    """MANIFEST.md records each file's SHA-256 at placement; the files are never modified."""
    recorded = dict(
        (name, digest)
        for digest, name in re.findall(
            r"^`([0-9a-f]{64})`\s+`([^`]+\.pdf)`$", (WEB / "MANIFEST.md").read_text("utf-8"), re.M
        )
    )
    pdfs = sorted(p.name for p in WEB.glob("*.pdf"))
    assert sorted(recorded) == pdfs
    for name in pdfs:
        assert hashlib.sha256((WEB / name).read_bytes()).hexdigest() == recorded[name], name


def test_repository_root_holds_no_web_transcription() -> None:
    assert not [p.name for p in ROOT.glob("0[0-7]_*")]


def test_superseded_web_files_are_06_and_07_and_no_clause_quotes_them() -> None:
    """Phase 6d: the official originals replace 06 and 07; the web files stay, unquoted."""
    from cascadeguard.knowledge.loader import load_clauses

    rows = (WEB / "MANIFEST.md").read_text("utf-8").splitlines()
    superseded = sorted(
        r.split("`")[1]
        for r in rows
        if r.endswith("| unverified; superseded by official original in policies/sources/ |")
    )
    assert superseded == ["06_unesco_ai_ethics_recommendation.pdf", "07_oecd_ai_principles.pdf"]
    quoted = {c.source_file for c in load_clauses()}
    assert not {f"web/{name}" for name in superseded} & quoted
    assert all((WEB / name).exists() for name in superseded)


def test_only_the_listed_two_column_original_is_read_by_column() -> None:
    """Phase 6d: UNESCO pages with a clear gutter are read column by column, so a paragraph is
    contiguous; no other extracted file carries "columns"."""
    script = extract_script()
    assert {
        "UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf"
    } == script.TWO_COLUMN
    split: dict[str, list[int]] = {}
    for path in sorted(EXTRACTED.glob("*.jsonl")):
        for line in path.read_text("utf-8").splitlines():
            record = json.loads(line)
            if record.get("columns"):
                split.setdefault(record["source_file"], []).append(record["page"])
    assert set(split) == set(script.TWO_COLUMN)
    unesco = EXTRACTED / "UNESCO Recommendation on the Ethics of Artificial Intelligence.jsonl"
    page = json.loads(unesco.read_text("utf-8").splitlines()[21])
    assert page["page"] == 22 and page["columns"] == 2
    assert (
        " ".join(page["text"].split()).count(
            "35. Member States should ensure that it is always possible to attribute ethical"
        )
        == 1
    )


def test_committed_originals_are_byte_identical_to_the_recorded_hashes() -> None:
    """Originals in policies/sources/ are never modified, renamed or deleted (AGENTS.md). The
    two books are not committed and are not recorded."""
    inventory = (ROOT / "docs" / "policy-inventory.md").read_text("utf-8")
    recorded = {
        name: digest
        for digest, name in re.findall(r"^`([0-9a-f]{64})`\s+`([^`]+\.pdf)`$", inventory, re.M)
    }
    sources = ROOT / "policies" / "sources"
    on_disk = sorted(
        p.name
        for p in sources.glob("*.pdf")
        if not any(m in p.name.casefold() for m in ("abhivardhan", "oxford handbook"))
    )
    assert len(recorded) == 20 and sorted(recorded) == on_disk
    for name in on_disk:
        assert hashlib.sha256((sources / name).read_bytes()).hexdigest() == recorded[name], name
