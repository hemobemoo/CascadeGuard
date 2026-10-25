# Phase 5 — clause triage

## Round 1 (2026-10-24): Phase 4 tail (a0b6342, 2f0ddc8, 9f27e4d, d96126b)

evidence-auditor verdict: **FAIL** (two MINOR findings, both fixed in the commit that adds this
file). Every quote matched `policies/extracted/` and a live pdfplumber read of the cited page;
telecom viewer page 14 was also checked against the page image.

| clause_id | result | note |
|---|---|---|
| uae.telecom-law.art6 | CLEAN | gaps skip footnote marker "1" only |
| uae.telecom-law.art14-5 | FIX → fixed | notes still described the dropped "authority uncertain" reading; now marked superseded (2026-10-24: no mapping, no authority on its own) |
| illus.telecom.incident-report | CLEAN | |
| illus.telecom.regulator-information-request | FIX → fixed | "can be retired in favour of art14-5" removed; art14-5 has no mapping and would not replace it |
| uae.pdpl.art9-1 | CLEAN | |
| uae.pdpl.art18-1 | CLEAN | |
| dha.pp11.applicability | NEEDS-HUMAN-JUDGMENT | binding unknown (3e) |
| dha.pp11.4-18-5 | NEEDS-HUMAN-JUDGMENT | actor from 4.18.4 (3p, open in clause review) |
| uae.ai-charter.safety | CLEAN | |
| mocai.ethics.contest-redress | CLEAN | MINOR, optional: gaps are right-column text of 3.4.2.2(c), acceptable |
| mocai.ethics.fallback-plan | NEEDS-HUMAN-JUDGMENT | interpreted actor/action (4d), clause review |
| itu.y3172.mlfo | CLEAN | |
| itu.y3172.req-ml-mng-003 | CLEAN | gap skips the margin requirement id |
| nist.ai-rmf.govern-2-1 | CLEAN | |
| nist.ai-rmf.manage-2-4 | CLEAN | |
| nist.ai-rmf.manage-4-3 | CLEAN | |
| eu.ai-act.art14-4-d | CLEAN | |
| eu.ai-act.art73-1 | CLEAN | |
| eu.ai-act.art73-3 | CLEAN | |
| eu.gdpr.art22-3 | CLEAN | |
| eu.gdpr.art33-1 | CLEAN | |
| oecd.ai-incidents.definition | CLEAN | |

The three NEEDS-HUMAN-JUDGMENT items are the existing open clause-review questions
(PROGRESS "Waiting on human" 1); nothing new.

## Round 4 (2026-10-26): 2f98197..0adff73

evidence-auditor verdict: **FAIL** (on code findings; all clauses verbatim). New clause:

| clause_id | result | note |
|---|---|---|
| uae.fl2-2019.art16-exceptions | NEEDS-HUMAN-JUDGMENT | Verbatim on extracted page 5 and in a live pdfplumber read; the full list (items 1-5; Article 17 follows); no gaps; no normalized block. Whether item 3 or 5 covers a share is legal interpretation. MINOR fixed: notes now spell out the binding scope. |

All other clauses re-confirmed CLEAN, or NEEDS-HUMAN-JUDGMENT as before (dha.pp11.applicability,
dha.pp11.4-18-5, mocai.ethics.fallback-plan); uae.telecom-law.art14-5 carried forward from round 1.

