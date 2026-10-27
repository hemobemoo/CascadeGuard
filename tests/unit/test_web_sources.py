"""Web transcriptions in policies/sources/web/: the manifest table and the extracted records."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "policies" / "sources" / "web"
EXTRACTED = ROOT / "policies" / "extracted"
HEADER = "| File | Official URL | Retrieved |\n|---|---|---|\n"


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
        "| `a.pdf` | https://example.org/a | 2026-10-27 |",
        "| `b.pdf` | https://example.org/b?x=1 | 2026-10-27 |",
    )
    urls = script.manifest_urls(manifest, ["a.pdf", "b.pdf"])
    assert urls == {"a.pdf": "https://example.org/a", "b.pdf": "https://example.org/b?x=1"}


@pytest.mark.parametrize(
    ("rows", "pdfs", "reason"),
    [
        (["| `a.pdf` | https://example.org/a | x |"], ["a.pdf", "b.pdf"], "no row"),
        (
            ["| `a.pdf` | https://e.org/a | x |", "| `c.pdf` | https://e.org/c | x |"],
            ["a.pdf"],
            "rows for files",
        ),
        (
            ["| `a.pdf` | https://e.org/a | x |", "| `a.pdf` | https://e.org/b | x |"],
            ["a.pdf"],
            "two rows",
        ),
        (["| `a.pdf` | http://example.org/a | x |"], ["a.pdf"], "https"),
        (["| `a.pdf` |  | x |"], ["a.pdf"], "https"),
        (["| `a.pdf` | https://e.org/a https://e.org/b | x |"], ["a.pdf"], "https"),
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
