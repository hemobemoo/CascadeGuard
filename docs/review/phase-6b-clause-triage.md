# Phase 6b clause triage (evidence-auditor, round 1, 2026-10-27)

Verdict: **PASS**. The branch `phase-6b-polish` changes no clause file (`git diff main...HEAD --
policies/` is empty). The auditor re-checked all 22 draft and illustrative clauses against the
extracted text and the PDFs (rendered page images for the OCR telecom page and MOCAI p.16).

| clause_id | viewer page | result | reason |
|---|---|---|---|
| dha.pp11.applicability | 1 | NEEDS-HUMAN-JUDGMENT | verbatim; `binding: unknown`: whether and on whom the policy binds is the human's decision |
| dha.pp11.4-18-5 | 32 | NEEDS-HUMAN-JUDGMENT | verbatim; normalized actor comes from 4.18.4 (mapping_note; decision 3p) |
| nist.ai-rmf.govern-2-1 | 3 | CLEAN | verbatim; binding false |
| nist.ai-rmf.manage-2-4 | 10 | CLEAN | verbatim; binding false |
| nist.ai-rmf.manage-4-3 | 10 | CLEAN | verbatim; binding false |
| eu.ai-act.art14-4-d | 61 | CLEAN | verbatim; chapeau qualifier in notes |
| eu.ai-act.art73-1 | 101 | CLEAN | verbatim |
| eu.ai-act.art73-3 | 102 | CLEAN | verbatim; "Notwithstanding paragraph 2" kept |
| eu.gdpr.art22-3 | 21 | CLEAN | verbatim |
| eu.gdpr.art33-1 | 29 | CLEAN | verbatim; "unless" qualifier kept; gap wording qualified |
| oecd.ai-incidents.definition | 11 | CLEAN | verbatim; omitted harms (c), (d) noted |
| itu.y3172.mlfo | 8 | CLEAN | verbatim |
| itu.y3172.req-ml-mng-003 | 18 | CLEAN | gap skips only the margin id |
| uae.ai-charter.safety | 1 | CLEAN | verbatim |
| mocai.ethics.contest-redress | 16 | CLEAN | both gaps skip item c text; no qualifier lost |
| mocai.ethics.fallback-plan | 16 | NEEDS-HUMAN-JUDGMENT | actor and action interpreted (`basis: interpreted`; decision 4d) |
| uae.pdpl.art9-1 | 13 | CLEAN | verbatim; trailing proviso in notes |
| uae.pdpl.art18-1 | 21 | CLEAN | verbatim; Art 18(2) qualifier in notes |
| uae.telecom-law.art6 | 11 | CLEAN | gaps skip footnote marker "1" and a stray extracted "1" (notes wording: deferred MINOR) |
| uae.telecom-law.art14-5 | 14 | CLEAN | matches the page image of the original |
| illus.telecom.incident-report | n/a | CLEAN | illustrative, binding false, not a quotation |
| illus.telecom.regulator-information-request | n/a | CLEAN | illustrative, binding false |

Gate 7, `scenarios/uae_health_access/display.yaml`: the incident summary is marked hypothetical
and synthetic, makes no legal claim and states no gap, conflict or applicability; the 8
category, 17 action and 3 goal labels are pure renames. Final approval of the summary wording
is the human's (spec 006b decision 3).
