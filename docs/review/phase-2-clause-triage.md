# Phase 2 clause triage

From the `evidence-auditor` runs on `phase-2-engine` (2026-10-23). Phase 2 changed no clause
text. It added synthetic fixture clauses (`tests/fixtures/clauses`), scenario data, and
diagnosis and report wording, which the auditor checked for unqualified legal claims.

## Verdicts

- Round 1: **FAIL**, MINOR only. Fixtures turned non-binding guidance into scenario rules;
  clause-note gaps (Art 16 item wording, PDPL binding scope, printed pages, Art 14(5) inferred
  counterpart and data category). All fixed.
- Round 2: **PASS**. No clause FIX, no BLOCKER or MAJOR. 13 clauses NEEDS-HUMAN-JUDGMENT, all
  already listed under "Waiting on human" in `PROGRESS.md`. 5 MINORs, all fixed: wording of the
  "uncertain" qualification, a stale PROGRESS line, the Art 9(1) translation note, the fixture
  `binding: unknown` exception (question 7u).

## Clause status after round 2 (31 clauses)

| Result | Clauses |
|---|---|
| NEEDS-HUMAN-JUDGMENT | `uae.fl2-2019.art2`, `art4`, `art6`, `art16`; `uae.pdpl.art2-2`; `dha.pp11.applicability`, `4-18-1`, `4-18-2`, `4-18-4`, `4-18-5`; `uae.telecom-law.art14-5` (OCR, checked against the page image) |
| CLEAN | `uae.pdpl.art9-1`, `art18-1`; `uae.telecom-law.art6`; both `illus.telecom.*`; both `uae.ai-charter.*`; both `mocai.ethics.*`; both `itu.y3172.*`; three `nist.ai-rmf.*`; three `eu.ai-act.*`; both `eu.gdpr.*`; `oecd.ai-incidents.definition` |
| FIX | none |

All 28 sourced quotes are verbatim on their cited page, both in the extracted text and in a live
PDF read. Every `[...]` gap skips only a margin ID, a footnote glyph or the facing-page column
(see `phase-1-clause-triage.md`). No book text was found anywhere, and no prompt injection.

## Questions raised for the human

- 7t: the engine reads `uae.fl2-2019.art16` and `art4` as a flat ban on sharing
  `patient_account_records`; the free-text condition is not evaluated.
- 7m: `uae.telecom-law.art14-5`, a power to issue rules read as a regulator permission, cited
  from the derived OCR copy.
- 7u: fixture-only exception for `binding: unknown` on illustrative clauses.
