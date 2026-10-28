# Spec 006d — Official sources (OECD, UNESCO, TRA-era cyber strategy)

Branch `phase-6d-official-sources`. Human instructions 2026-10-28. Re-anchor the 06 and 07
clauses to the official originals the human placed, without changing anything the engine, the
agents or the goldens see on the default path. All clauses stay `status: draft`; only the human
reviews them. No new dependency, no paid call, no download, no web scraping.

## a. Placement

- `OECD_Recommendation_AI.pdf` (OECD/LEGAL/0449), `UNESCO Recommendation on the Ethics of
  Artificial Intelligence.pdf` (SHS/BIO/PI/2021/1) and `UAE_National_Cybersecurity_Strategy.pdf`
  move from the repository root to `policies/sources/` (originals; names and bytes unchanged,
  SHA-256 checked before and after the move).
- Inventory rows #20–22 in `docs/policy-inventory.md`, with garbled and no-text pages flagged.

## b. Extraction

- `scripts/extract_pdf_text.py` extracts the three files. Re-extracting every existing source is
  byte-identical.
- UNESCO is two-column and pdfplumber interleaves its lines. It alone is listed in
  `TWO_COLUMN`: a page is read left column then right column when no word crosses the middle
  (record `"columns": 2`); other pages, and every other file, are read as before.

## c. Clauses

- Same ids, moved from `web_sources.yaml` to `international_precedents.yaml`, re-quoted
  verbatim from the originals: `unesco.ai-ethics.human-oversight` (paras 35–36),
  `unesco.ai-ethics.responsibility-accountability` (para 43; para 42 crosses pages 22–23, so its
  attribution sentence is quoted in notes), `oecd.ai-principles.robustness-override` (1.4 b),
  `oecd.ai-principles.accountability-cooperation` (1.5 c).
- New draft `unesco.ai-ethics.review-and-correct` (para 38): a designated staff member able to
  review and correct the decision. No normalized obligation.
- All `binding: false`, with each original's own wording in notes (UNESCO operative para 2,
  "apply on a voluntary basis"; OECD Legal Instruments, "not legally binding").
- `MANIFEST.md` marks 06 and 07 "unverified; superseded by official original in
  policies/sources/"; the web files stay. The 03 web transcription stays the only source for the
  2025 strategy; its two clauses are unchanged.
- The TRA-era strategy is undated (`unknown`), historical context, superseded by the 2025
  strategy. No clause is drafted from it.

## d. Impact check

`tests/integration/test_web_sources_impact.py`: on the default path, baseline, every role view and
LLM cache key, the repair search, replay views and both goldens are byte-identical with and
without the 6d drafts. With `--extracted-context`, the prompt-version fingerprint changes because
of the new extracted text (expected).

## e. Rule changes (gate 6, approved by the human)

`AGENTS.md`: "19" → "22" original PDF documents. `START_PROMPT.md`: Phase 6d and its Done when.

## Done when

Three originals placed and extracted, 06/07 clauses re-anchored, impact test passes, all checks
pass. The PR is opened and not merged (gates 1 and 6).
