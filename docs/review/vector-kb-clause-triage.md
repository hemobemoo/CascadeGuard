# Evidence triage: submission PR 3, vector knowledge base (branch `vector-kb`)

Evidence-auditor, round 1, 2026-10-30. **Verdict: PASS.** No clause file changed on this branch.
The auditor re-checked every draft and illustrative clause against the extracted text and the
PDF (pdfplumber), looked at the page images for Telecom Law p.14 and MOCAI p.16, and printed
the text each `[...]` skips. It also scanned `policies/kb/chunks.jsonl`: neither published book
appears in it, every chunk is labelled context only, and only reviewed clauses are attached,
each with its own status label.

| clause_id | source_file | viewer page | result | reason |
|---|---|---|---|---|
| dha.pp11.4-18-5 | Health Data Protection and Confidentiality Policy_EN2022810559.pdf | 32 | NEEDS-HUMAN-JUDGMENT | Verbatim. Actor from 4.18.4, outside the quote; `basis: interpreted`; closed by the human (3p; gate 1, kept as draft). Not loaded by the engine. |
| nist.ai-rmf.govern-2-1 | 5 AI RMF Core - Excerpt…(2023)..pdf | 3 | CLEAN | Verbatim. binding false. |
| nist.ai-rmf.manage-2-4 | same | 10 | CLEAN | Verbatim. binding false. |
| nist.ai-rmf.manage-4-3 | same | 10 | CLEAN | Verbatim. binding false. |
| eu.ai-act.art14-4-d | EU AI Act, Regulation (EU) 2024-1689.pdf | 61 | CLEAN | Verbatim; chapeau from p.60 in the notes. binding false. |
| eu.ai-act.art73-1 | same | 101 | CLEAN | Verbatim under the Article 73 heading. |
| eu.ai-act.art73-3 | same | 102 | CLEAN | Verbatim, "Notwithstanding paragraph 2" kept. |
| eu.gdpr.art22-3 | GDPR-Regulation (EU) 2016-679.pdf | 21 | CLEAN | Verbatim; notes say the consolidated text has no legal effect. |
| oecd.ai-incidents.definition | OCED-Towards a common reporting framework for AI incidents.pdf | 11 | CLEAN | Verbatim in Box 1.1. |
| itu.y3172.mlfo | T-REC-Y.3172-201906-I!!PDF-E.pdf | 8 | CLEAN | Verbatim. Printed page 2. |
| itu.y3172.req-ml-mng-003 | same | 18 | CLEAN | Gap skips only the margin ID. Printed page 12. |
| mocai.ethics.contest-redress | MOCAI-AI-Ethics-EN-1.pdf | 16 | CLEAN | Both gaps skip right-column text of 3.4.2.2(c) (image checked); notes record them. |
| mocai.ethics.fallback-plan | same | 16 | NEEDS-HUMAN-JUDGMENT | Verbatim. Actor not in the text; `basis: interpreted`; closed by the human (4d; gate 1). |
| uae.pdpl.art9-1 | Federal Decree by Law No. (45) of 2021…Personal Data.pdf | 13 | CLEAN | Verbatim. binding true, scope and Art 2(2) exclusions in the notes. |
| uae.pdpl.art18-1 | same | 21 | CLEAN | Verbatim; qualifiers and uncertain applicability in the notes. |
| uae.telecom-law.art6 | 887026278-TDRA-Telecom-Law-Final-English-o.pdf | 11 | CLEAN | Gaps skip a footnote marker and a stray "1". Printed page 09. |
| uae.telecom-law.art14-5 | ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf | 14 | CLEAN | Page image matches the quote word for word; OCR flag in the notes. |
| illus.telecom.incident-report | — | — | CLEAN | Illustrative, binding false, reason given. |
| illus.telecom.regulator-information-request | — | — | CLEAN | Same. |
| uae.mohap-smart-health.p2-coordination | web/01_uae_smart_health_ai_policy.pdf | 3 | CLEAN | Verbatim. binding unknown, with a reason. |
| uae.mohap-smart-health.p6-cybersecurity | same | 4 | CLEAN | Verbatim. binding unknown, with a reason. |
| uae.cyber-strategy-2025.governance-aim | web/03_uae_national_cybersecurity_strategy.pdf | 2 | NEEDS-HUMAN-JUDGMENT | Verbatim. Open question: Cabinet's own wording? (draft, open). |
| uae.cyber-strategy-2025.partnership-aim | same | 2 | NEEDS-HUMAN-JUDGMENT | Verbatim. Same open question. |

All four NEEDS-HUMAN-JUDGMENT items were already open or closed by the human before this
branch; nothing new.

## Findings beyond the clauses (MINOR, human choice; recorded in PROGRESS "Waiting on human")

- The 52 chunks from the TDRA OCR copy carry only "context only; not citable", though their OCR
  text has word-changing errors. Suggested: an OCR label.
- web/06 and web/07 are marked "superseded by official original" in MANIFEST.md but are still
  searched and indexed. Suggested: add them to `NOT_SEARCHED`, or say "superseded" in the label.
- Web chunks begin with the human's YAML headers (cleared in Phase 6c); they now also reach LLM
  agents through `--kb-context`. web/03's ingestion guidance is not indexed (NOT_SEARCHED).
