# Phase 3 evidence triage (evidence-auditor, round 1, 2026-10-23)

Verdict: **PASS**. Scope: the 20 draft and 2 illustrative clauses in `policies/reviewed/`
(the 9 reviewed clauses are unchanged and match `policies/approvals.yaml`), the Phase 3 diff,
and the Phase 2 commits 9bdd45a and 392f162. Quotes were checked against
`policies/extracted/` and a live read of each PDF page; `uae.telecom-law.art14-5` against the
rendered page image of the original.

| clause_id | viewer page | result | reason |
|---|---|---|---|
| dha.pp11.applicability | 1 | NEEDS-HUMAN-JUDGMENT | Verbatim; `binding: unknown` with a reason; applicability open (3d, 3e). |
| dha.pp11.4-18-5 | 32 | NEEDS-HUMAN-JUDGMENT | Verbatim (stops before a contact address). Actor taken from 4.18.4 outside the quote, disclosed (5h, 3p). |
| nist.ai-rmf.govern-2-1 | 3 | CLEAN | Verbatim, `binding: false`. |
| nist.ai-rmf.manage-2-4 | 10 | CLEAN | Verbatim, `binding: false`. |
| nist.ai-rmf.manage-4-3 | 10 | CLEAN | Verbatim, `binding: false`. |
| eu.ai-act.art14-4-d | 61 | CLEAN | Verbatim; chapeau on p. 60 cited in notes. |
| eu.ai-act.art73-1 | 101 | CLEAN | Verbatim, paragraph complete. |
| eu.ai-act.art73-3 | 102 | CLEAN | Verbatim, qualifiers kept. |
| eu.gdpr.art22-3 | 21 | CLEAN | Verbatim, cross-reference kept. |
| eu.gdpr.art33-1 | 29 | CLEAN | Verbatim, "unless" kept; note phrased as candidate finding. |
| oecd.ai-incidents.definition | 11 | CLEAN | Verbatim. Truncation after harm (b) now noted (fixed after round 1). |
| itu.y3172.mlfo | 8 | CLEAN | Verbatim, `binding: false`. |
| itu.y3172.req-ml-mng-003 | 18 | NEEDS-HUMAN-JUDGMENT | Verbatim (gap skips the requirement id). Design requirement mapped to `investigate_network_fault` on the operator (interpreted). |
| uae.ai-charter.safety | 1 | NEEDS-HUMAN-JUDGMENT | Verbatim. "encourages" mapped to a permission for the operator (interpreted; no authority effect as guidance). |
| mocai.ethics.contest-redress | 16 | CLEAN | Verbatim; gaps skip only the neighbouring column. |
| mocai.ethics.fallback-plan | 16 | NEEDS-HUMAN-JUDGMENT | Verbatim. Mapped to `activate_fallback_channel`; h2 mapped the analogous DHA duty to `maintain_fallback_plan`. |
| uae.pdpl.art9-1 | 13 | CLEAN | Verbatim; continuation in notes. |
| uae.pdpl.art18-1 | 21 | CLEAN | Verbatim; exceptions and scope in notes. |
| uae.telecom-law.art6 | 11 | CLEAN | Verbatim; gaps skip a footnote marker and an extraction artefact. |
| uae.telecom-law.art14-5 | 14 (OCR) | NEEDS-HUMAN-JUDGMENT | Matches the page image. Mapping note says "read as a permission"; 7m says not a permission in this incident (engine outcome matches 7m). |
| illus.telecom.incident-report | — | CLEAN | Illustrative, labelled, `binding: false`. |
| illus.telecom.regulator-information-request | — | CLEAN | Illustrative, labelled, `binding: false`. |

MINOR findings and what happened to them:
- Scripted uncertainty "No clause found that authorises this share." (uncited gap-style): removed;
  the 7r check now also covers such wording.
- CLI wording "no reviewed clause" vs. reviewed and binding: fixed.
- `uncertain: binding unknown` label on a non-binding obligation trigger: label now states the
  actual binding value.
- EU "unchanged by the 2026 amendment" notes without a URL: URL and "not in the reviewed corpus"
  added.
- OECD truncation not noted: noted.

The NEEDS-HUMAN-JUDGMENT items are listed in `PROGRESS.md`, "Waiting on human", item 4d.
