# Phase 6 clause triage (evidence-auditor, round 1, 2026-10-26)

Verdict: **PASS**. The diff changes no clause file. The 21 draft or illustrative clauses were
re-checked against the cited page of the extracted JSONL and a fresh pdfplumber read (the OCR
page of `uae.telecom-law.art14-5` against the rendered page image). The 10 reviewed clauses are
unchanged; `policies/approvals.yaml` lists none for re-approval.

| clause_id | viewer page | result | reason |
|---|---|---|---|
| dha.pp11.applicability | 1 | NEEDS-HUMAN-JUDGMENT | Verbatim; `binding: unknown` (open question 3e). |
| dha.pp11.4-18-5 | 32 | NEEDS-HUMAN-JUDGMENT | Verbatim; actor from 4.18.4 (decision 3p, clause review). |
| nist.ai-rmf.govern-2-1 | 3 | CLEAN | Verbatim; binding false. |
| nist.ai-rmf.manage-2-4 | 10 | CLEAN | Verbatim. |
| nist.ai-rmf.manage-4-3 | 10 | CLEAN | Verbatim. |
| eu.ai-act.art14-4-d | 61 | CLEAN | Verbatim; chapeau qualifier in notes. |
| eu.ai-act.art73-1 | 101 | CLEAN | Verbatim. |
| eu.ai-act.art73-3 | 102 | CLEAN | Verbatim; "Notwithstanding paragraph 2" kept. |
| eu.gdpr.art22-3 | 21 | CLEAN | Verbatim. |
| eu.gdpr.art33-1 | 29 | CLEAN | Verbatim; candidate-finding wording. |
| oecd.ai-incidents.definition | 11 | CLEAN | Verbatim; omissions noted. |
| itu.y3172.mlfo | 8 | CLEAN | Verbatim. |
| itu.y3172.req-ml-mng-003 | 18 | CLEAN | Gap skips only the requirement ID. |
| uae.ai-charter.safety | 1 | CLEAN | Verbatim; binding false. |
| mocai.ethics.contest-redress | 16 | CLEAN | Gaps are the neighbouring column. |
| mocai.ethics.fallback-plan | 16 | NEEDS-HUMAN-JUDGMENT | Actor/action interpreted (decision 4d). |
| uae.pdpl.art9-1 | 13 | CLEAN | Verbatim; scope in notes. |
| uae.pdpl.art18-1 | 21 | CLEAN | Verbatim; applicability flagged. |
| uae.telecom-law.art6 | 11 | CLEAN | Gaps skip footnote markers. |
| uae.telecom-law.art14-5 | 14 (OCR) | CLEAN | Checked against the page image. |
| illus.telecom.incident-report | n/a | CLEAN | Illustrative, labelled. |
| illus.telecom.regulator-information-request | n/a | CLEAN | Illustrative, labelled. |

QUESTION-FOR-HUMAN items: the three NEEDS-HUMAN-JUDGMENT clauses above (already open in the
human's clause review; no change suggested). Legal wording in the diff (evaluation finding,
spec, report, UI strings) is qualified; the disclaimer is in the header and at the foot.
