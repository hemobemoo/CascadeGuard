# Policy methodology

How CascadeGuard turns source documents into clauses the engine can check.

1. **Sources.** The 19 PDFs in `policies/sources/` are the knowledge base. They are never
   modified. The two published books (Abhivardhan; the Oxford Handbook) are context only: never
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
5. **Illustrative rules.** A rule the scenario needs that no PDF supports is written as
   `status: illustrative`, `binding: false`, with a plain-language text and a note on why it is
   needed. It is listed separately in phase reports and shown with its label in the UI.
6. **Loading.** The engine loads only `reviewed` and `illustrative` clauses
   (`knowledge.loader.load_engine_clauses`). A malformed file fails the whole load.

## Labelling rules

- Foreign law and international frameworks inform gap analysis; they are never UAE law
  (`binding: false`).
- A provision absent from the reviewed corpus is reported as "not found in the reviewed corpus",
  never as a confirmed legal gap.
- Applicability is stated in `notes`, not assumed. For example, the project's working reading,
  pending human review, is that the PDPL excludes health data that has its own legislation
  (`uae.pdpl.art2-2`, draft), so Federal Law No. 2 of 2019 (`uae.fl2-2019.art2`, draft) is the
  starting point for health data.
