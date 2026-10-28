# Phase 6d report — Official sources

Spec `specs/006d-official-sources.md`. Branch `phase-6d-official-sources`. Not merged: gates 1
(clause review) and 6 (rule edits) are for the human.

## What was done

- **Placement.** The three PDFs moved from the root to `policies/sources/`; SHA-256 equal before
  and after (`88227000…` OECD, `faf8887e…` UNESCO, `dd9767dc…` TRA strategy). 22 originals now.
- **Extraction.** All sources re-extracted: every existing `.jsonl` byte-identical (git shows no
  change); three new files and inventory entries. UNESCO is read column by column on the 20
  pages with a clear gutter (spec b).
- **Flagged, not guessed** (`docs/policy-inventory.md`, "Pages that need the human"): TRA strategy
  page 5 is scattered letters (circle diagram); pages 6–16 run diagram and table labels together
  (worst 7, 9, 11, 14, 16). UNESCO pages 8, 12, 16, 24 are divider images;
  pages 2, 4, 26, 27, 30, 33, 35–37, 39, 41–43 still interleave columns (full-width heading).
- **Clauses** (all draft, `binding: false`, no `normalized`):

| id | source | page | article |
|---|---|---|---|
| `unesco.ai-ethics.human-oversight` | UNESCO original | 22 | III.2, Human oversight and determination, paras 35–36 |
| `unesco.ai-ethics.review-and-correct` (new) | UNESCO original | 22 | III.2, Transparency and explainability, para 38 |
| `unesco.ai-ethics.responsibility-accountability` | UNESCO original | 23 | III.2, Responsibility and accountability, para 43 |
| `oecd.ai-principles.robustness-override` | OECD original | 9 | Section 1, 1.4 b) |
| `oecd.ai-principles.accountability-cooperation` | OECD original | 9 | Section 1, 1.5 c) |

  Gaps: `review-and-correct` skips only the page number "22" between the columns.
  `responsibility-accountability` first skipped the apostrophe in "whistle-blowers’"; on PR #11
  the human asked for the word quoted directly (see below).
  **Deviation:** para 42 runs from page 22 to 23 and a clause cites one page, so the clause quotes
  para 43 and gives para 42's attribution sentence verbatim in notes. Para 38 is a precedent for the
  candidate orphan duty (candidate finding: no owner for reviewing and reversing the lockouts was
  found in the reviewed corpus; cf. `unesco.ai-ethics.review-and-correct`,
  `uae.ai-charter.human-oversight`, `uae.pdpl.art18-1`).
- **MANIFEST.md:** 06 and 07 marked "unverified; superseded by official original in
  policies/sources/" (the parser accepts that status; tested). Web files kept; no clause quotes them.

## TRA-era strategy: passages for a historical-context clause

- **Health as a critical sector:** marginal. "Health" appears only as a label in the sector
  diagram (p.9) and the sector-prioritisation diagram (p.11), garbled; it would need the page image.
- **Information sharing between entities:** possibly. p.16, "cooperation and effectiveness of
  response teams information sharing and exchange between TRA and the entities", but it is
  regulator–entity sharing, not operator-to-operator, and the line joins two columns.
- **Incident response teams:** marginal. p.6 ("Respond and Recover", "Incident Response
  capabilities") and p.16 are diagram labels; the scenario's regulator notice is already the
  illustrative clause.

## Impact check (spec d)

- **Default path:** `test_default_path_is_byte_identical_without_the_6d_drafts` — baseline, every
  view and LLM cache key, the repair search and replay views byte-identical; goldens match
  (`test_goldens_still_match_with_the_web_drafts_present`). The draft-count line goes 29 → 30
  (one new draft).
- **`--extracted-context`:** fingerprint `765eb44c26f0` → `ef1611888f36` because of the new
  extracted text, then `cbfe8170a200` once the TRA-era strategy is excluded (human decision on PR
  #11). Expected, not a failure: any decision cached with the option on is asked again.
- **Once reviewed:** the five clauses reach only `policy_legal_adviser` (tested), changing its
  views and cache keys (a new paid run of its steps, gate 4).

## Human decisions on PR #11 (2026-10-28)

- Para 42/43 deviation accepted; gate-6 edits confirmed.
- TRA-era strategy excluded from `--extracted-context` retrieval and the extracted digest
  (`NOT_SEARCHED`), with tests that no snippet from it is returned; reason recorded in
  `docs/policy-inventory.md`. No historical-context clause.
- `unesco.ai-ethics.responsibility-accountability` quotes "whistle-blowers’ protection" with no
  gap; the plain quote check passes. **Correction:** the round-1 report, triage and notes said
  this apostrophe, and some OECD/UNESCO apostrophes and the TRA bullets, extract as U+FFFD. They
  do not: the three extractions contain no U+FFFD (they hold U+2019 and U+2022). The Windows
  console showed them as "�". Those statements are removed.
- `mocai.ethics.contest-redress` notes give the text its two `[...]` skip.
- Deferred test-breaker MINORs logged under "Open items" in `PROGRESS.md`.
