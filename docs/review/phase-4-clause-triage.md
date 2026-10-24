# Phase 4 clause triage (evidence-auditor, round 2, 2026-10-24)

**Verdict: PASS.** No clause or scenario file changed in Phase 4. The auditor checked the 22
`draft` and `illustrative` clauses against `policies/extracted/` and a live read of each PDF
page, and scanned the Phase 4 diff for legal claims (none found).

| Clause id | Viewer page | Result | Reason |
|---|---|---|---|
| dha.pp11.applicability | 1 | CLEAN | Exact match; `binding: unknown` with reason. |
| dha.pp11.4-18-5 | 32 | NEEDS-HUMAN-JUDGMENT | Exact match; actor comes from 4.18.4 outside the quote (disclosed; 3p, in the human's clause review). |
| nist.ai-rmf.govern-2-1 | 3 | CLEAN | Exact match; `binding: false`. |
| nist.ai-rmf.manage-2-4 | 10 | CLEAN | Exact match; `binding: false`. |
| nist.ai-rmf.manage-4-3 | 10 | CLEAN | Exact match; `binding: false`. |
| eu.ai-act.art14-4-d | 61 | CLEAN | Exact match; chapeau quoted in the note. |
| eu.ai-act.art73-1 | 101 | CLEAN | Exact match. |
| eu.ai-act.art73-3 | 102 | CLEAN | Exact match. |
| eu.gdpr.art22-3 | 21 | CLEAN | Exact match. |
| eu.gdpr.art33-1 | 29 | CLEAN | Exact match; gap worded as a candidate finding. |
| oecd.ai-incidents.definition | 11 | CLEAN | Exact match; truncation disclosed. |
| itu.y3172.mlfo | 8 | CLEAN | Exact match. |
| itu.y3172.req-ml-mng-003 | 18 | CLEAN | Exact match; gap skips only the margin requirement id; no `normalized` (4d). |
| uae.ai-charter.safety | 1 | CLEAN | Exact match; no `normalized` (4d). |
| mocai.ethics.contest-redress | 16 | CLEAN | Exact match; gaps skip only neighbouring-column item c (listed for the human). |
| mocai.ethics.fallback-plan | 16 | CLEAN | Exact match; mapping disclosed as interpretation (4d). |
| uae.pdpl.art9-1 | 13 | CLEAN | Exact match; cut disclosed. |
| uae.pdpl.art18-1 | 21 | CLEAN | Exact match; Art 18(2) qualifier disclosed. |
| uae.telecom-law.art6 | 11 | CLEAN | Exact match; gaps are footnote markers. |
| uae.telecom-law.art14-5 | 14 (OCR) | NEEDS-HUMAN-JUDGMENT | Matches the OCR text; image check is the human's; `kind: permission` sits uneasily with 7m. |
| illus.telecom.incident-report | n/a | CLEAN | Illustrative, labelled, not a quotation. |
| illus.telecom.regulator-information-request | n/a | CLEAN | Illustrative, labelled, not a quotation. |

QUESTION-FOR-HUMAN items: 3p for `dha.pp11.4-18-5` (already in clause review); for
`uae.telecom-law.art14-5`, the image check and whether `kind: permission` should stay given 7m
(or the `normalized` block be dropped as for the ITU and Charter clauses); the skipped column
text in `mocai.ethics.contest-redress`, for the record.
