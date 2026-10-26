# ADR 0002 option A: clause triage (evidence-auditor, round 1, 2026-10-26)

Verdict: **PASS**. Scope: the 23 draft or illustrative clauses in `policies/reviewed/` plus
`uae.fl2-2019.art16-exceptions` (set to reviewed in 98cbd85). Each quote was checked against
the cited page in `policies/extracted/` and a live pdfplumber read of the PDF.

| clause_id | viewer page | result | reason |
|---|---|---|---|
| dha.pp11.applicability | 1 | NEEDS-HUMAN-JUDGMENT | Verbatim; `binding: unknown` (3e open). |
| dha.pp11.4-18-5 | 32 | NEEDS-HUMAN-JUDGMENT | Verbatim; actor taken from 4.18.4 (3p open). |
| nist.ai-rmf.govern-2-1 | 3 | CLEAN | Verbatim; binding false. |
| nist.ai-rmf.manage-2-4 | 10 | CLEAN | Verbatim; binding false. |
| nist.ai-rmf.manage-4-3 | 10 | CLEAN | Verbatim; binding false. |
| eu.ai-act.art14-4-d | 61 | CLEAN | Verbatim; binding false. |
| eu.ai-act.art73-1 | 101 | CLEAN | Verbatim; binding false. |
| eu.ai-act.art73-3 | 102 | CLEAN | Verbatim; binding false. |
| eu.gdpr.art22-3 | 21 | CLEAN | Verbatim; binding false. |
| eu.gdpr.art33-1 | 29 | CLEAN | Verbatim; qualifier kept. |
| oecd.ai-incidents.definition | 11 | CLEAN | Verbatim; truncation noted. |
| itu.y3172.mlfo | 8 | CLEAN | Verbatim; binding false. |
| itu.y3172.req-ml-mng-003 | 18 | CLEAN | Gap skips only the requirement ID. |
| uae.ai-charter.safety | 1 | CLEAN | Verbatim; binding false. |
| mocai.ethics.contest-redress | 16 | CLEAN | Gaps are right-column text (column crop). |
| mocai.ethics.fallback-plan | 16 | NEEDS-HUMAN-JUDGMENT | Actor/action from decision 4d. |
| uae.fl2-2019.art16-exceptions | 5 | CLEAN | Reviewed by the human; verbatim, items 1-5 complete, no gaps, no normalized. |
| uae.pdpl.art9-1 | 13 | CLEAN | Verbatim; scope stated. |
| uae.pdpl.art18-1 | 21 | CLEAN | Verbatim; applicability flagged. |
| uae.telecom-law.art6 | 11 | CLEAN | Gaps skip footnote markers. |
| uae.telecom-law.art14-5 | 14 (OCR) | CLEAN | Matches OCR page; no mapping. |
| illus.telecom.incident-report | n/a | CLEAN | Illustrative, labelled. |
| illus.telecom.regulator-information-request | n/a | CLEAN | Illustrative, labelled. |

Findings: QUESTION (approval of art16-exceptions): answered, the human listed it in chat on
2026-10-26 (recorded in `phase-5-clause-triage.md`). MINOR (stale lines): fixed. MINOR (repair
rule label in `open_obligations` lacks "; not citable"): kept, because the human set that label;
the engine still rejects a citation of a repair rule as `unknown_citation`.
