# Phase 6d — clause triage (evidence-auditor)

Branch `phase-6d-official-sources`. Round 1 verdict: **FAIL** on one MAJOR (an unqualified
orphan-duty sentence in `docs/review/phase-6d-report.md`, fixed). No clause FIX. All 32 quotes
verbatim on their cited page in the extracted JSONL and in the PDF page; the two-column UNESCO
and MOCAI pages also read column by column; the OCR clause checked against the page image.

## Phase 6d clauses (all draft, `binding: false`, no `normalized`)

| clause_id | source_file | page | result | reason |
|---|---|---|---|---|
| unesco.ai-ethics.human-oversight | UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf | 22 | CLEAN | Paras 35–36 verbatim, no gap; non-binding wording from operative para 2 (p.7). |
| unesco.ai-ethics.review-and-correct (new) | same | 22 | CLEAN | Para 38 verbatim; `[...]` skips only the page number "22". |
| unesco.ai-ethics.responsibility-accountability | same | 23 | CLEAN | Para 43 verbatim; ~~`[...]` skips one U+FFFD~~ (superseded, see round 3); para 42 sentence in notes matches pp.22–23. |
| oecd.ai-principles.robustness-override | OECD_Recommendation_AI.pdf | 9 | CLEAN | 1.4 b) verbatim; dates (p.3) and "not legally binding" (p.12) match. |
| oecd.ai-principles.accountability-cooperation | same | 9 | CLEAN | 1.5 c) verbatim; ends at a sentence boundary. |

## Earlier clauses

CLEAN: all NIST, EU AI Act, GDPR, OECD incidents, ITU, Charter, MOCAI contest-redress, PDPL,
telecom, illustrative and `uae.mohap-smart-health.*` clauses. NEEDS-HUMAN-JUDGMENT (unchanged):
`dha.pp11.applicability`, `dha.pp11.4-18-5`, `mocai.ethics.fallback-plan`,
`uae.cyber-strategy-2025.governance-aim`, `uae.cyber-strategy-2025.partnership-aim` (whether the
wording is the Cabinet's own; the TRA-era PDF does not answer it).

## Findings, round 1

- **MAJOR (fixed)** — report stated the orphan duty without qualification; now a candidate
  finding citing `unesco.ai-ethics.review-and-correct`, `uae.ai-charter.human-oversight`,
  `uae.pdpl.art18-1`.
- **MINOR (fixed)** — `review-and-correct` notes now give the same qualified wording with cf. ids.
- **MINOR (fixed)** — OECD notes and PROGRESS: "the PDF lists no Adherents; UAE adherence not
  checked" (it has no Adherents list).
- **MINOR (deferred to review)** — `eu.gdpr.art33-1` title drops "where feasible".
- **MINOR (fixed)** — this triage file now exists.
- **QUESTION-FOR-HUMAN** — DHA applicability, DHA 4.18.5 actor (3p), MOCAI fallback mapping
  (4d), 03 attribution: in the review list in `PROGRESS.md`.

## Round 2

Verdict **PASS**. No FIX; same CLEAN / NEEDS-HUMAN-JUDGMENT split. UNESCO pp.22–23 and the
telecom p.14 quote checked against page images. MINORs left for review: quote
"whistle-blowers' protection" instead of the one-character `[...]` (U+FFFD), or keep it; add the
skipped MOCAI 3.4.2.2(c) text to `mocai.ethics.contest-redress` notes; `eu.gdpr.art33-1` title.

## Round 3 (human decisions on PR #11, changed clauses only)

**Correction to rounds 1–2:** the "U+FFFD" in row `responsibility-accountability` and in the
round-2 MINOR was a console-encoding misreading; page 23 has U+2019 there, and the three 6d
extractions contain no U+FFFD.

Verdict **PASS** (scope: the two changed clauses).

| clause_id | source_file | page | result | reason |
|---|---|---|---|---|
| unesco.ai-ethics.responsibility-accountability | UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf | 23 | CLEAN | Para 43 verbatim with no gap, in the JSONL and a crop of PDF p.23; "whistle-blowers’" is U+2019 in both; para 42 sentence in notes confirmed. |
| mocai.ethics.contest-redress | MOCAI-AI-Ethics-EN-1.pdf | 16 | CLEAN | Pieces in order; the notes give the two skipped texts exactly (3.4.2.2(c), neighbouring column); no qualifier hidden. |

MINOR (fixed): the round-1 row for `responsibility-accountability` still described a `[...]`
gap; marked superseded.
