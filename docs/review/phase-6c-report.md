# Phase 6c report — Policy source expansion

Spec `specs/006c-policy-sources.md`. Branch `phase-6c-policy-sources`. Human decisions
2026-10-28: gate 6 approved; gate 1 deferred until the official documents are placed; merge on
reviewer PASS and green CI.

## What was done

- **Placement.** The seven PDFs moved from the root to `policies/sources/web/` with their
  filenames; SHA-256 equal before and after the move. `00_manifest.md` became
  `policies/sources/web/MANIFEST.md`: the human's note kept unchanged under a new table (official
  URL, retrieval date 2026-10-27, issuer, document date, type, "unverified"). Nothing else in
  `policies/sources/` changed. The root is clean.
- **Extraction.** `scripts/extract_pdf_text.py` reads `web/*.pdf`, takes each URL from the
  manifest table (missing, duplicate, unknown-file or non-https rows stop it), and writes
  `"web": true` and `"source_url"` on every page record and inventory entry (plus
  `"manifest": "web/MANIFEST.md"` in the inventory). Every web page has extractable text. The
  originals were re-extracted in the same run and are byte-identical.
- **Loader.** `source_file: web/<name>.pdf` passes the existing path check, and the
  verbatim-on-page check reads `policies/extracted/<stem>.jsonl` like any other source. New rule
  in `PolicyClause` (mirrors OCR): a web clause must say "web transcription — unverified" in
  `notes` and cannot be `binding: true`. Tests in `tests/unit/test_clause_loader.py` and
  `tests/unit/test_web_sources.py`.
- **Clauses.** `policies/reviewed/web_sources.yaml`: nine drafts, none with a `normalized`
  reading: the three 01 clauses `binding: unknown` ("national public policy; legal effect not
  verified", human decision 2026-10-28), the other six `binding: false`. Each quote is verbatim on its page (repository test).

## Draft clauses and their link to the cascade

| Clause | Source, page | Link to `uae_health_access` |
|---|---|---|
| `uae.mohap-smart-health.p2-coordination` | 01, p.3 | Context for the telecom → health information deadlock (`network_incident_status`); authorises no share. |
| `uae.mohap-smart-health.p6-cybersecurity` | 01, p.4 | Context for the health operator's security incident at T+15 on a suspected (unconfirmed) alert; no reporting duty, regulator or deadline. |
| `uae.mohap-smart-health.p7-liability` | 01, p.4 | Context for the orphan duty to review and reverse the automated lockouts: an aim to set liability frameworks, not a framework, and it names no owner (candidate finding; cf. `uae.ai-charter.human-oversight`, `uae.pdpl.art18-1`). |
| `uae.cyber-strategy-2025.governance-aim` | 03, p.2 | Strategy-level context for two security incidents handled without a shared escalation path. |
| `uae.cyber-strategy-2025.partnership-aim` | 03, p.2 | Strategy-level context for the cross-sector deadlock. |
| `unesco.ai-ethics.human-oversight` | 06, p.4 | Precedent for a human owner of the lockout review and reversal. |
| `unesco.ai-ethics.responsibility-accountability` | 06, p.4 | Precedent for tracing the lockouts back to the telecom model update. |
| `oecd.ai-principles.robustness-override` | 07, p.3 | Precedent for suspending the traffic model and reversing the lockouts. |
| `oecd.ai-principles.accountability-cooperation` | 07, p.4 | Precedent for co-operation between the two AI actors. |

The 01 and 03 quotes are single list items; the heading of each priority is in `article`.

**02, 04, 05 — kept as sources only.**
- 02 (International AI policy): about the UAE's international AI stance; nothing in the scenario's
  incident handling needs it.
- 04 (Digital Government Strategy 2025): government service design dimensions (inclusive by
  default, resilient); the fallback-channel rule already has a closer (non-binding, draft)
  source, `mocai.ethics.fallback-plan`.
- 05 (AI in government policies): AI CEOs, councils and programmes for ministries and federal
  entities; the scenario's portal operator is non-governmental (scenario assumption 3c).

## Impact check (spec 006c d)

**Today, as drafts:** drafts are never loaded by the engine, so nothing the engine or an agent sees
changes. `tests/integration/test_web_sources_impact.py` compares a run with the drafts against a
run on a copy of `policies/reviewed/` without them: the scripted baseline result, the loaded
clause list, every role view at every step and its LLM cache key (baseline and every replay of
the repair search), and the repair search are byte-identical; both goldens still match.
Visible differences, none in a golden:

1. The "N draft clauses not loaded (awaiting human review)" line (CLI, Markdown export, UI
   Expert section) goes from 20 to 29.
2. An LLM agent that cites one of the new ids now gets a `draft_citation` rejection instead of an
   unknown-citation rejection (the id is now in the corpus). No cached decision cites them.
3. `--extracted-context` (opt-in, off by default) searches every non-book `policies/extracted/*.jsonl`,
   so the seven web files can now appear as snippets. Human decision 2026-10-28: they stay
   searchable, and each web snippet is labelled "web transcription — unverified; context only; not
   citable". With the option on, the prompt version carries a digest of the searchable extracted
   corpus, so a changed corpus never reuses a cached decision. With it off nothing changes.

**Once reviewed (per clause; the same for all nine):**

| Question | Answer |
|---|---|
| Enters a role's view (`clauses_for_role`)? | Only `policy_legal_adviser`'s: with no `normalized` reading a clause concerns no role or action (`RuleBook.concerns`), except for roles allowed `provide_policy_analysis`, which may cite any loaded clause. That role is the only one (tested). |
| Changes LLM cache keys? | Yes, for `policy_legal_adviser` at every step, baseline and replays: its cached decisions would not be reused, and a new LLM run of those steps would need live (paid) calls. No other role's view or key changes. |
| Changes the scripted baseline? | No: no scripted decision cites them, and without `normalized` they give no authority, restriction, share basis or obligation. The clause-set list in outputs grows. |
| Changes repair ranking? | No: none of the nine has a reading the search or hard filter could use, and the golden search still matched with one of them marked reviewed (scratch run). |
| Changes a golden? | No (checked by marking one clause reviewed in a scratch run: the goldens still matched; the byte-identity test failed on the adviser's view, as intended). |

## Questions and downloads for the human

- **06 UNESCO, 07 OECD:** the transcriptions are web page summaries. Before review, download and
  place the instruments: UNESCO *Recommendation on the Ethics of Artificial Intelligence*,
  SHS/BIO/PI/2021/1; OECD *Recommendation of the Council on Artificial Intelligence*,
  OECD/LEGAL/0449 (2024 revision). The clauses would then be re-quoted from them.
- **03 Cybersecurity Strategy:** yes, download the Cyber Security Council strategy PDF (URL in
  `MANIFEST.md`) and place it in `policies/sources/` as an original: the current file is two
  announcements, and only the strategy text could support anything beyond context. The National
  Cyber Security Policy for AI (also linked) would help the scenario more directly, since the
  cascade starts with two AI models (its summary lists AI monitoring and response); a summary of
  it is already in `UAE Policy Foundation.pdf` pp. 5-7; no clause is drafted from those pages.
- **`--extracted-context` and web files:** answered 2026-10-28 (included, labelled; see above).

## Human decisions, 2026-10-28

Embedded YAML headers and 03 "ingestion guidance" are the human's own metadata: files confirmed
as they are, evidence-auditor BLOCKER cleared by the human. No clause reviewed now (all nine
stay draft until re-anchored to the originals). 01 `binding: unknown`. Web snippets included and
labelled. Illustrative clauses may not name a `source_file` (no existing clause affected: none
does). Impact-test rewrite after gate 1 approved in advance. Gate 6 wording approved.
