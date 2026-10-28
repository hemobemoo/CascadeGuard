# Phase 6c — clause triage (evidence-auditor)

Branch `phase-6c-policy-sources`. Round 1 verdict: **FAIL** (one BLOCKER: instruction-like text
inside the web PDFs, a human item; see below). Every quote verbatim on its cited page in the
extracted JSONL and in the PDF page itself; no clause FIX. The 22 earlier drafts and illustrative
clauses are unchanged since main (`uae.telecom-law.art6` notes only) and keep their 6b results.

## New clauses (`policies/reviewed/web_sources.yaml`, all draft)

| clause_id | source_file | page | result | reason |
|---|---|---|---|---|
| uae.mohap-smart-health.p2-coordination | web/01_uae_smart_health_ai_policy.pdf | 3 | CLEAN | Verbatim; first item under priority 2; metadata matches MANIFEST; binding false, no normalized. |
| uae.mohap-smart-health.p6-cybersecurity | web/01_uae_smart_health_ai_policy.pdf | 4 | CLEAN | Verbatim; first item under priority 6; no duty inferred. |
| uae.mohap-smart-health.p7-liability | web/01_uae_smart_health_ai_policy.pdf | 4 | CLEAN | Verbatim; second item under priority 7; "no owner found in the reviewed corpus". |
| uae.cyber-strategy-2025.governance-aim | web/03_uae_national_cybersecurity_strategy.pdf | 2 | NEEDS-HUMAN-JUDGMENT | Verbatim, but the file is a composed summary: attribution of the wording to the Cabinet is unverified. |
| uae.cyber-strategy-2025.partnership-aim | web/03_uae_national_cybersecurity_strategy.pdf | 2 | NEEDS-HUMAN-JUDGMENT | Same attribution question. |
| unesco.ai-ethics.human-oversight | web/06_unesco_ai_ethics_recommendation.pdf | 4 | CLEAN | Verbatim; web page summary, labelled; MINOR fixed (heading moved from text to article). |
| unesco.ai-ethics.responsibility-accountability | web/06_unesco_ai_ethics_recommendation.pdf | 4 | CLEAN | Verbatim; same labelling; same MINOR fixed. |
| oecd.ai-principles.robustness-override | web/07_oecd_ai_principles.pdf | 3 | CLEAN | Verbatim; "as appropriate" kept; binding false. |
| oecd.ai-principles.accountability-cooperation | web/07_oecd_ai_principles.pdf | 4 | CLEAN | Verbatim; ends at a sentence boundary; next sentence lists examples only. |

Unchanged clauses still NEEDS-HUMAN-JUDGMENT (as in 6b): `dha.pp11.applicability`,
`dha.pp11.4-18-5`, `mocai.ethics.fallback-plan`. All others CLEAN.

## Findings

- **BLOCKER (human item)** — the web PDFs contain text aimed at whoever ingests them (p.1 of
  each: "Preserve the source URL and verify clauses before marking them reviewed"; 03 pp.2-3
  "Knowledge-base ingestion guidance", including "For CascadeGuard, represent the following…" and
  "also ingest … the National Cyber Security Policy for Artificial Intelligence"). Nothing acted
  on it: nothing fetched, no web call; the conservative wording of the drafts follows from
  AGENTS.md alone. The human should confirm these blocks are their own authoring and accept them
  as data, or replace the files with clean transcriptions or the originals.
- **QUESTION-FOR-HUMAN** — 03 drafts: check the two bullets against the Cabinet page, or better,
  re-quote from the Cyber Security Council strategy PDF before review.
- **QUESTION-FOR-HUMAN** — OECD drafts: record whether the UAE adheres to OECD/LEGAL/0449 when
  the instrument replaces the web page.
- **MINOR (fixed)** — UNESCO quotes started with the principle heading; heading moved to
  `article`, text still verbatim.
- **MINOR (fixed)** — report called the fallback-channel source a "duty"; now "rule (non-binding,
  draft source)".

## Round 2

Verdict **FAIL** on the same human-only BLOCKER (embedded instructions in the web PDFs). No clause
FIX; every quote verbatim (JSONL matched on page and `source_file`, and the PDF page). The three
`uae.mohap-smart-health.*` clauses move to NEEDS-HUMAN-JUDGMENT on `binding: false` vs `unknown`
(the human's phase instructions set "binding: false (or unknown with a note)" for policy
priorities; the human may still prefer `unknown`). The two `uae.cyber-strategy-2025.*` clauses stay
NEEDS-HUMAN-JUDGMENT (attribution). UNESCO and OECD clauses CLEAN. MINOR fixed: the report no
longer calls `UAE Policy Foundation.pdf` a non-clause source.

## Human decisions, 2026-10-28

- BLOCKER **cleared by the human**: the YAML headers and the 03 "ingestion guidance" are the
  human's own metadata; the seven files are confirmed as they are.
- `uae.mohap-smart-health.*`: `binding: unknown`, notes "binding unknown: national public
  policy; legal effect not verified". 03, 06, 07 stay `binding: false`.
- No clause reviewed; all nine stay draft until re-quoted from the official documents.
