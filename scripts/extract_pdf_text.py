"""Extract page-by-page text from the policy PDFs.

Reads every PDF in policies/sources/ (read-only) and writes
policies/extracted/<pdf-stem>.jsonl with one {"source_file", "page", "text"} record per page,
plus policies/extracted/_inventory.json summarising page counts, metadata and pages without
extractable text (likely scanned images; these must be flagged to the human, never guessed).

OCR'd copies in policies/sources/ocr/ are derived sources: each record also carries
"ocr": true, source_file is "ocr/<name>", and the inventory entry names the original it was
derived from. OCR text must be corrected against the page image before it is quoted.

Web transcriptions in policies/sources/web/ (official web pages printed to PDF, unverified) are
marked the same way: each record carries "web": true and the page's "source_url", taken from
the table in policies/sources/web/MANIFEST.md, and source_file is "web/<name>". A web PDF with
no manifest row (or a malformed row) stops the extraction.

Usage: uv run python scripts/extract_pdf_text.py [--only <substring>]
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "policies" / "sources"
OCR_SOURCES = SOURCES / "ocr"  # OCR'd copies of originals, named <original-stem>.ocr.pdf
WEB_SOURCES = SOURCES / "web"  # web-page transcriptions, listed in MANIFEST.md
MANIFEST = WEB_SOURCES / "MANIFEST.md"
EXTRACTED = ROOT / "policies" / "extracted"
INVENTORY = EXTRACTED / "_inventory.json"

# A page with fewer non-whitespace characters than this is reported as having no usable text.
MIN_TEXT_CHARS = 20
# A manifest table row: | `<file>.pdf` | URL | Retrieved | Issuer | Document date | Type | Status |
MANIFEST_ROW = re.compile(r"^\|\s*`([^`]+\.pdf)`\s*\|")
MANIFEST_COLUMNS = 7
DOCUMENT_TYPES = frozenset(
    {"law", "policy", "strategy", "ethical principle", "international precedent"}
)
RETRIEVED = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _real_date(text: str) -> bool:
    """A YYYY-MM-DD calendar date ("2026-13-45" is refused)."""
    if not RETRIEVED.match(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


class ManifestError(ValueError):
    """MANIFEST.md does not list every web PDF exactly once with an https URL."""


def manifest_urls(manifest: Path, pdf_names: list[str]) -> dict[str, str]:
    """The official URL of each web PDF, from the manifest table. Strict: every PDF has exactly
    one row, every row names a PDF that exists, and every URL starts with https://."""
    urls: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = MANIFEST_ROW.match(line)
        if match is None:
            continue
        name = match.group(1)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if name in urls:
            raise ManifestError(f"{manifest.name}: two rows for {name}")
        if len(cells) != MANIFEST_COLUMNS:
            raise ManifestError(f"{manifest.name}: {name} needs {MANIFEST_COLUMNS} columns")
        _, url, retrieved, issuer, document_date, kind, status = cells
        if urlsplit(url).scheme != "https" or not urlsplit(url).netloc or " " in url:
            raise ManifestError(f"{manifest.name}: {name} has no single https:// URL")
        if not _real_date(retrieved) or not issuer or not document_date:
            raise ManifestError(f"{manifest.name}: {name} needs retrieval date, issuer and date")
        if kind not in DOCUMENT_TYPES:
            raise ManifestError(f"{manifest.name}: {name} has unknown document type {kind!r}")
        if status != "unverified":
            raise ManifestError(f"{manifest.name}: {name} status must be 'unverified'")
        urls[name] = url
    if missing := sorted(set(pdf_names) - set(urls)):
        raise ManifestError(f"{manifest.name}: no row for {missing}")
    if unknown := sorted(set(urls) - set(pdf_names)):
        raise ManifestError(f"{manifest.name}: rows for files not in web/: {unknown}")
    return urls


def extract_pdf(pdf_path: Path, source_url: str | None = None) -> dict[str, Any]:
    out_path = EXTRACTED / f"{pdf_path.stem}.jsonl"
    source_file = pdf_path.relative_to(SOURCES).as_posix()
    ocr = pdf_path.parent == OCR_SOURCES
    web = source_url is not None
    empty_pages: list[int] = []
    image_only_pages: list[int] = []
    with pdfplumber.open(pdf_path) as pdf, out_path.open("w", encoding="utf-8") as out:
        # pdfplumber leaves PDF.metadata untyped.
        raw_metadata = cast(dict[str, Any], pdf.metadata)  # pyright: ignore[reportUnknownMemberType]
        metadata = {k: str(v) for k, v in raw_metadata.items()}
        page_count = len(pdf.pages)
        for number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if len("".join(text.split())) < MIN_TEXT_CHARS:
                empty_pages.append(number)
                if page.images:
                    image_only_pages.append(number)
            record: dict[str, Any] = {"source_file": source_file, "page": number, "text": text}
            if ocr:
                record["ocr"] = True
            if web:
                record["web"] = True
                record["source_url"] = source_url
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            page.close()
    entry: dict[str, Any] = {
        "source_file": source_file,
        "output": out_path.name,
        "page_count": page_count,
        "pages_without_text": empty_pages,
        "image_pages_without_text": image_only_pages,
        "metadata": {k: metadata[k] for k in ("Title", "Author", "CreationDate") if k in metadata},
    }
    if ocr:
        entry["ocr"] = True
        entry["derived_from"] = pdf_path.name.removesuffix(".ocr.pdf") + ".pdf"
    if web:
        entry["web"] = True
        entry["source_url"] = source_url
        entry["manifest"] = MANIFEST.relative_to(SOURCES).as_posix()
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract page-by-page text from the policy PDFs.")
    parser.add_argument("--only", help="extract only PDFs whose filename contains this text")
    args = parser.parse_args()

    EXTRACTED.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if INVENTORY.exists():
        existing = {e["source_file"]: e for e in json.loads(INVENTORY.read_text("utf-8"))}

    web_pdfs = sorted(WEB_SOURCES.glob("*.pdf"))
    urls = manifest_urls(MANIFEST, [p.name for p in web_pdfs]) if web_pdfs else {}
    pdfs = sorted(SOURCES.glob("*.pdf")) + sorted(OCR_SOURCES.glob("*.ocr.pdf")) + web_pdfs
    # Output files are named by stem, so two sources with one stem would overwrite each other.
    stems = [p.stem.casefold() for p in pdfs]  # Windows and macOS ignore case
    if clashes := sorted({s for s in stems if stems.count(s) > 1}):
        raise SystemExit(f"two source PDFs share an extracted name: {clashes}")
    if args.only:
        pdfs = [p for p in pdfs if args.only in p.name]
    for pdf_path in pdfs:
        url = urls.get(pdf_path.name) if pdf_path.parent == WEB_SOURCES else None
        entry = extract_pdf(pdf_path, url)
        existing[entry["source_file"]] = entry
        print(
            f"{entry['page_count']:5d} pages, {len(entry['pages_without_text']):4d} without text"
            f"  {entry['source_file']}"
        )

    inventory = [existing[name] for name in sorted(existing)]
    INVENTORY.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
