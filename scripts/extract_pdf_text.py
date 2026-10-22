"""Extract page-by-page text from the policy PDFs.

Reads every PDF in policies/sources/ (read-only) and writes
policies/extracted/<pdf-stem>.jsonl with one {"source_file", "page", "text"} record per page,
plus policies/extracted/_inventory.json summarising page counts, metadata and pages without
extractable text (likely scanned images; these must be flagged to the human, never guessed).

Usage: uv run python scripts/extract_pdf_text.py [--only <substring>]
"""

import argparse
import json
from pathlib import Path
from typing import Any, cast

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "policies" / "sources"
EXTRACTED = ROOT / "policies" / "extracted"
INVENTORY = EXTRACTED / "_inventory.json"

# A page with fewer non-whitespace characters than this is reported as having no usable text.
MIN_TEXT_CHARS = 20


def extract_pdf(pdf_path: Path) -> dict[str, Any]:
    out_path = EXTRACTED / f"{pdf_path.stem}.jsonl"
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
            record = {"source_file": pdf_path.name, "page": number, "text": text}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            page.close()
    return {
        "source_file": pdf_path.name,
        "output": out_path.name,
        "page_count": page_count,
        "pages_without_text": empty_pages,
        "image_pages_without_text": image_only_pages,
        "metadata": {k: metadata[k] for k in ("Title", "Author", "CreationDate") if k in metadata},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract page-by-page text from the policy PDFs.")
    parser.add_argument("--only", help="extract only PDFs whose filename contains this text")
    args = parser.parse_args()

    EXTRACTED.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if INVENTORY.exists():
        existing = {e["source_file"]: e for e in json.loads(INVENTORY.read_text("utf-8"))}

    pdfs = sorted(SOURCES.glob("*.pdf"))
    if args.only:
        pdfs = [p for p in pdfs if args.only in p.name]
    for pdf_path in pdfs:
        entry = extract_pdf(pdf_path)
        existing[pdf_path.name] = entry
        print(
            f"{entry['page_count']:5d} pages, {len(entry['pages_without_text']):4d} without text"
            f"  {pdf_path.name}"
        )

    inventory = [existing[name] for name in sorted(existing)]
    INVENTORY.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
