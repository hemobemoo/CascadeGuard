# Policy methodology

How CascadeGuard turns source documents into clauses the engine can check.

1. **Sources.** The 23 original PDFs in `policies/sources/`, plus the web transcriptions in
   `policies/sources/web/` (listed in its `MANIFEST.md`, see 5b), are the knowledge base. They
   are never modified. The two published books (Abhivardhan; the Oxford Handbook) are context only: never
   a clause source and never committed.
2. **Extraction.** `uv run python scripts/extract_pdf_text.py` writes page-by-page text to
   `policies/extracted/<pdf-stem>.jsonl` and an inventory to `policies/extracted/_inventory.json`.
   Pages with no extractable text are listed there and reported to the human. Their text is never
   guessed.
3. **Drafting.** An agent drafts clauses in `policies/reviewed/*.yaml`, only for provisions the
   scenario needs, quoting verbatim from the extracted page, with `status: draft`. Omissions are
   marked `[...]`. The test suite verifies each quote against its cited page.
4. **Review.** The human checks each draft against the PDF itself (text, page, article, issuer,
   date, `binding`, and the `normalized` reading) and sets `status: reviewed`. Agents never do this.
5. **Derived OCR sources.** An OCR'd copy of an original goes to `policies/sources/ocr/` as
   `<original-stem>.ocr.pdf`; the original is never replaced or renamed. It is extracted to its
   own `policies/extracted/<original-stem>.ocr.jsonl` with `"ocr": true` on every page, and the
   inventory entry names the original it was `derived_from`. OCR text is not trusted: any quote
   from an OCR page is corrected against the page image of the original PDF, the clause's
   `source_file` is `ocr/<name>`, `page` is the PDF page index (the printed page goes in
   `notes`), and `notes` must contain "OCR — check against image" (the loader rejects the clause
   otherwise). The clause is flagged the same way in the review list.
5b. **Web transcriptions.** Official web pages printed to PDF by the human go to
   `policies/sources/web/`, each with one row in `MANIFEST.md` (official URL, retrieval date,
   issuer, document date, document type, "unverified"). They are not the original documents.
   The extraction script reads the URL from the manifest table (a missing or malformed row
   stops it) and marks every page record and inventory entry `"web": true` with its
   `source_url`. A clause quoting one has `source_file: web/<name>.pdf`, says "web
   transcription — unverified" in `notes`, and is never `binding: true` (the loader rejects it
   otherwise). Where the transcription is only a summary of a document (UNESCO, OECD, the
   Cybersecurity Strategy announcements), the original document should replace it before the
   clause is reviewed.
5c. **Page-image transcriptions** (human decision 2026-10-29). Where an original renders its text as
   images or outlines over an unreliable text layer (the Charter, #23), the agent transcribes only the pages a clause
   needs, from the page image, into `policies/transcriptions/<pdf-stem>.jsonl` (one record per
   page: `source_file`, `page`, `text`, `"transcribed": true`, `"transcribed_from": "page image"`,
   `"status": "draft"`). A clause quoted from it says "transcribed from page image — check against
   image" in `notes` and is checked against the transcription, never the text layer. The human
   checks the transcription against the image when reviewing the clause; the same "Reviewed by
   human" commit sets the transcription's `status` to `reviewed`. Only the sources in
   `TRANSCRIBED_SOURCES` (`domain/policies.py`, each marked unreliable in the inventory) may be
   transcribed.
6. **Illustrative rules.** A rule the scenario needs that no PDF supports is written as
   `status: illustrative`, `binding: false`, with a plain-language text and a note on why it is
   needed. It is listed separately in phase reports and shown with its label in the UI.
7. **Loading.** The engine loads only `reviewed` and `illustrative` clauses
   (`knowledge.loader.load_engine_clauses`). A malformed file fails the whole load.

## OCR provenance

| Derived file | Original | Supplied | Provenance | Known OCR errors |
|---|---|---|---|---|
| `policies/sources/ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf` (sha256 `cda5693f…`, 47 pages) | `887026278-TDRA-Telecom-Law-Final-English-o.pdf` (sha256 `f6c6d4a9…`, unchanged) | By the human, 2026-10-22 (first committed in 0a51f82 over the original by mistake; moved to `ocr/` in 428e114) | PDF metadata: ModDate 2026-10-22 21:18:56 UTC, Producer "macOS Version 12.1 (Build 21C52) Quartz PDFContext". The OCR tool is not recorded. | Words run together; broken list markers (e.g. "?", "I", "i" for item numbers, "5Requesting"); footnote digits stuck to words ("Board'", "(14)1,2"); swapped or interleaved paragraphs (human-reported: Art 28, Art 64/65, Art 14 item 21, Art 71/72 on printed page 37); misread footers. PDF page index = printed page + 2 on pages 5–47. |

## Labelling rules

- Foreign law and international frameworks inform gap analysis; they are never UAE law
  (`binding: false`).
- A provision absent from the reviewed corpus is reported as "not found in the reviewed corpus",
  never as a confirmed legal gap.
- Applicability is stated in `notes`, not assumed. For example, the project's working reading,
  pending human review, is that the PDPL excludes health data that has its own legislation
  (`uae.pdpl.art2-2`, draft), so Federal Law No. 2 of 2019 (`uae.fl2-2019.art2`, draft) is the
  starting point for health data.
