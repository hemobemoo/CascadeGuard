# Phase 1 clause triage

Review list for the human, from the `evidence-auditor` runs on `phase-1-domain-scenario`
(2026-10-22, rounds 1–3). 30 clauses: 28 `draft`, 2 `illustrative`, none `reviewed`. Every
non-illustrative quote was found verbatim on its cited viewer page, both in `policies/extracted/`
and in a live pdfplumber read of the PDF. No book text appears in any clause, scenario or doc file
(10-word overlap check; the only overlap, GDPR Art 22(3), is taken from the GDPR PDF). No prompt
injection was found in the source text.

Review the **minimal core set** first (the engine needs it for the real baseline), then the rest.
This core-first order is the human's instruction (2026-10-22); it overrides START_PROMPT 1e's
global NEEDS-HUMAN-JUDGMENT-first order, so `dha.pp11.applicability` and `dha.pp11.4-18-5`
(NEEDS-HUMAN-JUDGMENT, not core) come in Part 2.
Within each part: NEEDS-HUMAN-JUDGMENT, then FIX, then CLEAN. "Resolved" means fixed on this
branch; "open (5h)" means the fix depends on the human's answer to question 5h in the PR (how
`normalized` may map text onto the scenario's action catalogue). "Page" is the PDF viewer page
(1-based). Binding-scope and translation notes were added to every `binding: true` UAE clause, and
every DHA clause now points to `dha.pp11.applicability` for its `binding: unknown`.

## Part 1 — minimal core set

| # | Clause id | PDF | Page | Triage | What to check |
|---|---|---|---|---|---|
| 1 | `uae.fl2-2019.art2` | UAE Federal Law No. 2 of 2019 … Health Fields..pdf | 2 | NEEDS-HUMAN-JUDGMENT | Applicability is a legal reading. The note now says "treated as applicable for this scenario, pending human review" (fixed in round 2; round 1 had wrongly reported it fixed). English translation. |
| 2 | `uae.fl2-2019.art4` | same | 3 | NEEDS-HUMAN-JUDGMENT | Are lock records with mobile numbers (`patient_account_records`) "health data and information"? Decides whether the engine blocks the mobile-number share. Note now admits `share_incident_status` is a mapping. |
| 3 | `uae.pdpl.art2-2` | Federal Decree by Law No. (45) of 2021 … Personal Data.pdf | 6 | NEEDS-HUMAN-JUDGMENT | Is FL 2/2019 "legislation regulating [health data's] protection and processing" under Art 2(2)(e)? Is the operator governmental (2(2)(b))? Note now a working reading; mentions (f) and (g) (free zones, pp.6–7). |
| 4 | `dha.pp11.4-18-2` | Health Data Protection and Confidentiality Policy_EN2022810559.pdf | 31 | NEEDS-HUMAN-JUDGMENT | `raise_security_incident` maps "investigate" (5h). Item bb ("Determine if further investigation is warranted …") now noted. |
| 5 | `uae.fl2-2019.art6` | UAE Federal Law No. 2 of 2019 … | 3 | FIX resolved + question | "shall set" read as a power; `issue_determination` marked as a mapping. **Question:** the translation defines "Health Authority" twice (p.2); read literally, the second could make the portal operator a "Health Authority". Check the Arabic. |
| 6 | `uae.fl2-2019.art16` | same | 4 | FIX resolved + question | Condition no longer imports the p.5 exceptions. Same "Health Authority" question; the parse of "not to use them except in the health purposes without written approval" is ambiguous in translation. |
| 7 | `dha.pp11.4-18-4` | Health Data Protection and Confidentiality Policy_EN2022810559.pdf | 32 | FIX resolved | Notes now cite the policy's own definition of "UAE Data Protection Law" as Decree-Law 45/2021 and its supersession sentence (§4.2, pp.9–10). Recipient comes from 4.18.5. |
| 8 | `dha.pp11.4-18-1` | same | 30 | FIX open (5h) | Obligation to `activate_fallback_channel` is not entailed: the text obliges entities to *establish* plans, and items a–h do not mention a fallback. |
| 9 | `uae.ai-charter.human-oversight` | UAE Policy Foundation.pdf | 2 | FIX open (5h) | Actor and action are not in the text (notes admit the mapping). Issuer/date per your decision. |
| 10 | `illus.telecom.incident-report` | — illustrative | — | CLEAN | binding false, plain language, no source file; the 60-minute deadline is a labelled scenario assumption. |
| 11 | `illus.telecom.regulator-information-request` | — illustrative | — | CLEAN | Same. |

## Part 2 — other clauses

| # | Clause id | PDF | Page | Triage | What to check |
|---|---|---|---|---|---|
| 12 | `dha.pp11.applicability` | Health Data Protection and Confidentiality Policy_EN2022810559.pdf | 1 | NEEDS-HUMAN-JUDGMENT | Does the policy bind a DHA-licensed private operator? Scope §3.5 (p.9): "All users accessing and using health information in healthcare sector in the Emirate of Dubai". Cover says Effective 10/10/2022, footer says Nov 10, 2022; `document_date` uses the issue date 2022-08-10. |
| 13 | `dha.pp11.4-18-5` | same | 32 | NEEDS-HUMAN-JUDGMENT | The text names "both the UAE Information Office and DHA"; the mapping keeps only DHA. "confirmed or suspected" in the condition extends "Breach notifications". |
| 14 | `uae.telecom-law.art6` | 887026278-TDRA-Telecom-Law-Final-English-o.pdf | 11 | FIX resolved | Binding scope and "English consolidated version, Arabic not checked" added. Gaps below. Footnote 1 = TRA→TDRA rename by Decree-Law 23/2020. |
| 15 | `itu.y3172.req-ml-mng-003` | T-REC-Y.3172-201906-I!!PDF-E.pdf | 18 | FIX open (5h) | Text: "The ML architecture is required to support capabilities"; `normalized` puts an obligation on `telecom_operator` to `investigate_network_fault`. Gap below. |
| 16 | `uae.ai-charter.safety` | UAE Policy Foundation.pdf | 1 | FIX open (5h) | `kind: permission`, actor and action are not in "The country encourages modifying or removing systems that pose risks." |
| 17 | `mocai.ethics.fallback-plan` | MOCAI-AI-Ethics-EN-1.pdf | 16 | FIX open (5h) | Actor and action are not in "AI systems should have safeguards that enable a fallback plan in case of problems." |
| 18 | `uae.pdpl.art9-1` | Federal Decree by Law No. (45) of 2021 … | 13 | CLEAN (round 2) | Scope, truncated proviso and candidate overlap are stated. |
| 19 | `uae.pdpl.art18-1` | same | 21 | CLEAN (round 2) | Art 18(2) and 18(4) noted. |
| 20 | `eu.ai-act.art14-4-d` | EU AI Act, Regulation (EU) 2024-1689.pdf | 61 | CLEAN (round 2) | Chapeau qualifier noted. |
| 21 | `eu.ai-act.art73-3` | same | 102 | CLEAN (round 2) | 3(49)(b) quoted with "irreversible". |
| 22 | `eu.gdpr.art33-1` | GDPR-Regulation (EU) 2016-679.pdf | 29 | CLEAN (round 2; was MAJOR) | Gap claim qualified and cited; consolidated-text caveat added. |
| 23 | `mocai.ethics.contest-redress` | MOCAI-AI-Ethics-EN-1.pdf | 16 | CLEAN (round 2) | Article 3.4.2.1(d) confirmed on pp.15–16. Gaps below (glyph positions confirm the facing page). |
| 24 | `nist.ai-rmf.govern-2-1` | 5 AI RMF Core … (2023)..pdf | 3 | CLEAN | |
| 25 | `nist.ai-rmf.manage-2-4` | same | 10 | CLEAN | |
| 26 | `nist.ai-rmf.manage-4-3` | same | 10 | CLEAN | |
| 27 | `eu.ai-act.art73-1` | EU AI Act … | 101 | CLEAN | Paragraph complete; p.102 starts with "2." |
| 28 | `eu.gdpr.art22-3` | GDPR … | 21 | CLEAN | Consolidated-text caveat added. |
| 29 | `oecd.ai-incidents.definition` | OCED-Towards a common reporting framework for AI incidents.pdf | 11 | CLEAN | Box 1.1; cover prints "February 2025 No. 34". |
| 30 | `itu.y3172.mlfo` | T-REC-Y.3172-201906-I!!PDF-E.pdf | 8 | CLEAN | |

## `[...]` gaps and the text each one skips

| Clause id | Gap | Skipped text |
|---|---|---|
| `itu.y3172.req-ml-mng-003` | 1 | `REQ-ML-MNG-003` (margin requirement ID) |
| `mocai.ethics.contest-redress` | 1 | `c In the case that such explanations are available, they should be easily and quickly accessible,` (right-hand printed page 31, item c of 3.4.2.2; x ≥ 699 on the spread) |
| `mocai.ethics.contest-redress` | 2 | `free of charge and user-friendly.` (same column) |
| `uae.telecom-law.art6` | 1 | `1` (7-pt footnote marker after "Authority”") |
| `uae.telecom-law.art6` | 2 | `1` (a second 7-pt "1" glyph overlapping "entrusted") |

## Findings outside clauses

- **Resolved:** scenario README gap bullets cite clause IDs, say "not found in the reviewed corpus
  (Telecom Law pp.13-47 unreadable)", mark clauses draft/unreviewed, and are candidate findings.
  The mandate-overlap bullet cites DHA §4.2's supersession sentence.
- **Resolved:** README "Applicable health-data regime", PROGRESS "Decisions" and
  `docs/policy-methodology.md` state applicability as the project's working reading of draft
  clauses, pending human review.
- **Resolved:** PROGRESS's Dubai Law 26/2015 note reads as the agent's reading.
- **Deferred MINOR:** `scenario.yaml:9` "nobody owns reversing the locks" is a hypothetical
  premise; never cite it as a corpus finding.
- **QUESTION-FOR-HUMAN:** the DHA PDF footers read "n/52" but the PDF has 50 pages, ending in the
  references (5.23). Printed pages 51–52 may be missing. No clause depends on them.

## Reviewer verdicts

- Round 1 — evidence-auditor **FAIL** (3 MAJOR); phase-auditor **FAIL** (2 MAJOR). Fixed in ad59827.
- Round 2 — evidence-auditor **FAIL** (2 MAJOR: art2 note not actually reworded; DHA §4.2
  definition and supersession omitted); phase-auditor **FAIL** (3 MAJOR: art2 note; PDPL art2-2
  note; methodology applicability line). All fixed in the round-2 commit.
- Round 3 — evidence-auditor **FAIL, no BLOCKER or MAJOR**: 6 clauses stay FIX only on question
  5h (`normalized` mapping); new MINORs. phase-auditor **PASS** (all "Done when" criteria proven;
  MINORs and human questions only). The round limit is reached: 5h is a human gate.
- After round 3 (not re-reviewed): MINOR wording fixes. `dha.pp11.4-18-5` condition no longer
  adds "suspected"; `uae.fl2-2019.art4` condition says "including, but not limited to, Art 16";
  `uae.ai-charter.safety` and `mocai.ethics.fallback-plan` notes mark their mapping (and the
  fallback condition is now "in case of problems"); `scenario.yaml` summary marks the lock
  ownership as a hypothetical premise; Telecom header notes page 4. `dha.pp11.4-18-5` therefore
  moves from FIX back to NEEDS-HUMAN-JUDGMENT (recipient mapping).
