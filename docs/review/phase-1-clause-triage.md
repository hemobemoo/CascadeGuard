# Phase 1 clause triage

Review list for the human, from the `evidence-auditor` run on `phase-1-domain-scenario`
(2026-10-22). 30 clauses: 28 `draft`, 2 `illustrative`, none `reviewed`. Every non-illustrative
quote was found verbatim on its cited viewer page, both in `policies/extracted/` and in a live
pdfplumber read of the PDF. No book text appears in any clause or scenario file. No prompt
injection was found in the source text.

Review the **minimal core set** first (the engine needs it for the real baseline), then the rest.
Within each part: NEEDS-HUMAN-JUDGMENT, then FIX (resolved in this branch), then CLEAN.
"Page" is the PDF viewer page (1-based).

## Part 1 — minimal core set

| # | Clause id | PDF | Page | Triage | What to check |
|---|---|---|---|---|---|
| 1 | `uae.fl2-2019.art2` | UAE Federal Law No. 2 of 2019 … Health Fields..pdf | 2 | NEEDS-HUMAN-JUDGMENT | The note's "so this law applies" is a legal reading (now worded "treated as applicable for this scenario"). English translation. |
| 2 | `uae.fl2-2019.art4` | same | 3 | NEEDS-HUMAN-JUDGMENT | Are lock records with mobile numbers (`patient_account_records`) "health data and information"? Decides whether the engine blocks the mobile-number share. |
| 3 | `uae.pdpl.art2-2` | Federal Decree by Law No. (45) of 2021 … Personal Data.pdf | 6 | NEEDS-HUMAN-JUDGMENT | Is FL 2/2019 "legislation regulating [health data's] protection and processing" under Art 2(2)(e)? Is the portal operator governmental (exclusion b)? |
| 4 | `uae.fl2-2019.art6` | UAE Federal Law No. 2 of 2019 … | 3 | FIX (resolved) + question | Notes now say "shall set" is read as a power (kind permission) and that `issue_determination` is the scenario's action id. **Question:** the translation defines "Health Authority" twice (p.2); read literally, the second could make the portal operator a "Health Authority". Check the Arabic. |
| 5 | `uae.fl2-2019.art16` | same | 4 | FIX (resolved) + question | Condition no longer imports the p.5 exceptions or misparses the text: health purposes; other use needs written approval, except the cases on p.5 (not quoted). Same "Health Authority" question. |
| 6 | `dha.pp11.4-18-1` | Health Data Protection and Confidentiality Policy_EN2022810559.pdf | 30 | FIX (resolved) | Notes now say the listed plan contents (pp.30–31) do not mention a fallback channel; `activate_fallback_channel` is a mapping. |
| 7 | `dha.pp11.4-18-2` | same | 31 | FIX (resolved) | Condition is now "from discovery of a breach or incident until closure"; "suspected" is marked as the scenario's word, not the policy's. |
| 8 | `dha.pp11.4-18-4` | same | 32 | FIX (resolved) + question | Notes now say the recipient comes from 4.18.5. **Question:** is "Executive Regulations of UAE Data Protection Law" those of Decree-Law 45/2021? (4.18.10, p.33, uses the same reference.) |
| 9 | `uae.ai-charter.human-oversight` | UAE Policy Foundation.pdf | 2 | FIX (resolved) | Notes now say actor and action are the scenario's mapping. Issuer and date set per the human's decision (AI Office, 2024-07, binding false). |
| 10 | `illus.telecom.incident-report` | — (illustrative) | — | CLEAN | binding false, plain language, no source file; note gives the reason. |
| 11 | `illus.telecom.regulator-information-request` | — (illustrative) | — | CLEAN | Same. |

## Part 2 — other clauses

| # | Clause id | PDF | Page | Triage | What to check |
|---|---|---|---|---|---|
| 12 | `dha.pp11.applicability` | Health Data Protection and Confidentiality Policy_EN2022810559.pdf | 1 | NEEDS-HUMAN-JUDGMENT | Does a DHA policy bind a DHA-licensed private operator? All DHA clauses are `binding: unknown`. Cover says Effective 10/10/2022, footer says Nov 10, 2022; `document_date` uses the issue date 2022-08-10. |
| 13 | `dha.pp11.4-18-5` | same | 32 | NEEDS-HUMAN-JUDGMENT | The text names "both the UAE Information Office and DHA"; the mapping keeps only DHA. Who is the "UAE Information Office", and is dropping it acceptable? "suspected" in the condition is an interpretation. |
| 14 | `eu.ai-act.art14-4-d` | EU AI Act, Regulation (EU) 2024-1689.pdf | 61 | FIX (resolved) | Notes now quote the Art 14(4) chapeau (p.60, "as appropriate and proportionate"): a design duty on the provider. |
| 15 | `eu.ai-act.art73-3` | same | 102 | FIX (resolved) | Notes now quote Art 3(49)(b) with "irreversible" (p.49). |
| 16 | `eu.gdpr.art33-1` | GDPR-Regulation (EU) 2016-679.pdf | 29 | FIX (resolved, was MAJOR) | Unqualified corpus-gap claim replaced by "not found in the reviewed corpus … candidate finding", citing dha.pp11.4-18-4 and uae.pdpl.art9-1, and noting DHA 4.18.10 and 4.18.7. |
| 17 | `mocai.ethics.contest-redress` | MOCAI-AI-Ethics-EN-1.pdf | 16 | FIX (resolved) | `article` set to 3.4.2.1(d); note gives the soft "could consider" context. Gaps below. |
| 18 | `uae.pdpl.art9-1` | Federal Decree by Law No. (45) of 2021 … | 13 | FIX (resolved) | Notes now give scope (subject to Art 2(2)), mark the truncated "provided that …" proviso, and call the overlap a candidate finding. |
| 19 | `uae.pdpl.art18-1` | same | 21 | FIX (resolved) | Notes now give the Art 18(2) exceptions and Art 18(4) (Controller reviews automated decisions on request). |
| 20 | `itu.y3172.req-ml-mng-003` | T-REC-Y.3172-201906-I!!PDF-E.pdf | 18 | FIX (deferred, MINOR) | `normalized` actor/action/condition come from the table's Notes row, not the quote ("The ML architecture is required to support capabilities"). Gap below. |
| 21 | `uae.ai-charter.safety` | UAE Policy Foundation.pdf | 1 | FIX (deferred, MINOR) | `kind: permission`, actor and action are not in the text ("The country encourages modifying or removing systems that pose risks"). Issuer/date set per the human's decision. |
| 22 | `mocai.ethics.fallback-plan` | MOCAI-AI-Ethics-EN-1.pdf | 16 | FIX (deferred, MINOR) | `normalized` actor and action are not in the text ("AI systems should have safeguards that enable a fallback plan in case of problems"). Article 3.5.1, DEC 2022 confirmed. |
| 23 | `nist.ai-rmf.govern-2-1` | 5 AI RMF Core … (2023)..pdf | 3 | CLEAN | |
| 24 | `nist.ai-rmf.manage-2-4` | same | 10 | CLEAN | |
| 25 | `nist.ai-rmf.manage-4-3` | same | 10 | CLEAN | |
| 26 | `eu.ai-act.art73-1` | EU AI Act … | 101 | CLEAN | Paragraph complete; p.102 starts with "2." |
| 27 | `eu.gdpr.art22-3` | GDPR … | 21 | CLEAN | |
| 28 | `oecd.ai-incidents.definition` | OCED-Towards a common reporting framework for AI incidents.pdf | 11 | CLEAN | Cover prints "February 2025 No. 34". |
| 29 | `itu.y3172.mlfo` | T-REC-Y.3172-201906-I!!PDF-E.pdf | 8 | CLEAN | |
| 30 | `uae.telecom-law.art6` | 887026278-TDRA-Telecom-Law-Final-English-o.pdf | 11 | CLEAN | Gaps below. Footnote 1 = TRA→TDRA rename by Decree-Law 23/2020. |

## `[...]` gaps and the text each one skips

| Clause id | Gap | Skipped text |
|---|---|---|
| `itu.y3172.req-ml-mng-003` | 1 | `REQ-ML-MNG-003` (margin requirement ID) |
| `mocai.ethics.contest-redress` | 1 | `c In the case that such explanations are available, they should be easily and quickly accessible,` (right-hand column, item c of 3.4.2.2) |
| `mocai.ethics.contest-redress` | 2 | `free of charge and user-friendly.` (same column) |
| `uae.telecom-law.art6` | 1 | `1` (footnote marker) |
| `uae.telecom-law.art6` | 2 | `1` (footnote marker) |

## Findings outside clauses (round 1)

- **MAJOR, resolved:** `scenarios/uae_health_access/README.md` "Orphan duty" and "Mandate overlap"
  stated gaps and conflicts as fact without clause IDs. They now cite clause IDs, say "not found in
  the corpus", mark the clauses draft/unreviewed, and are labelled candidate findings. The orphan
  duty now mentions PDPL Art 18(4).
- **QUESTION-FOR-HUMAN:** README "Applicable health-data regime" and PROGRESS "Decisions" said FL
  2/2019 and the DHA policy "apply". Now worded as the project's working reading of draft clauses
  ("treated as applicable"), pending the human's confirmation.
- **MINOR, resolved:** PROGRESS's Dubai Law 26/2015 note now reads as the agent's reading, not a
  legal conclusion.
- **MINOR, deferred:** `scenario.yaml:9` says "nobody owns reversing the locks". Acceptable as a
  hypothetical premise; it must not be cited later as a corpus finding.

## Reviewer verdicts

Filled in after each round; see the PR body for the final verdicts.

- Round 1: evidence-auditor **FAIL** (3 MAJOR, all resolved above); phase-auditor **FAIL**
  (2 MAJOR: this triage file missing, PR body out of date).
