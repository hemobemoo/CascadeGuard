# Task 3 triage: UAE Cyber Security Council sources (2026-11-06)

Branch `uae-cyber-sources`. Human brief of 2026-11-05 and instructions of 2026-11-06. The three
PDFs were downloaded by the human from the official csc.gov.ae links. They are **not
redistributed**: each says "Neither the whole nor part of this document shall be reproduced
without the prior written consent of the UAE Cyber Security Council." So they are gitignored with
their extracted text, and pinned by SHA-256 (`docs/policy-inventory.md`, #25–27) and per-page text
digests (`policies/not_redistributed_pages.json`). The short verbatim quotes are only in
`policies/gap_examples_only/uae_csc_cyber.yaml`; this file does not repeat them.

## Decisions (human, 2026-11-06)

- Gate 1: the human checked all seven quotes against the PDFs (verbatim, pages correct). Five are
  reviewed as gap examples only; `uae.csc-cirp.ncrg-level3-declaration` and
  `uae.csc-cirp.ncrg-sector-impact-information` stay drafts (they map to no failure).
- Legal status, in every note and (short form) in every relevance line: ISF and CIRP
  "Cabinet-approved national framework/plan (as printed on its cover); legal force for this
  scenario not established"; AI policy "Council-approved national policy (as printed on its
  cover); legal force for this scenario not established". `binding: unknown` kept.
- Gate 7: the six entries below approved with the legal-status short form added; the
  sector-impact entry dropped. The final lines are in `scenarios/uae_health_access/gap_examples.yaml`.
- Gate 6: the AGENTS.md wording below, approved and applied.
- The generated gap analysis and the report name these clauses without reproducing their text.

## Sources (version as printed, not the file name)

| Source | Version as printed (cover) | File name | Pages |
|---|---|---|---|
| National Cyber Security Policy for Artificial Intelligence | November 2025, Version 1.1 | `... v1.1.pdf` | 55 |
| Cyber Security Information Sharing Framework | May 2023, Version 1.0 | `... V2.0.pdf` (mismatch) | 44 |
| Cyber Incident Response Plan | May 2023, Version 1.0 | `... V2.0.pdf` (mismatch) | 50 |

Some pages of the AI policy also carry "Implementation Guidance Version 1.0" in their header
(e.g. 3.4.3), inside the Version 1.1 document. Printed page = PDF page − 1 for every quoted page.

## Drafts for gate 1 (all `status: draft`, in `policies/gap_examples_only/`, never loaded)

Labels for every one: UAE text; issuer UAE Cyber Security Council; jurisdiction "UAE (federal;
federal entities and CII entities)"; `binding: unknown` (shown as "draft · binding unknown"); the
notes give the scope ("applies to federal entities and CII entities, for cybersecurity of AI/ML
systems or cybersecurity information") and why binding is unknown here (the scenario's operators
are not designated CII, and the incident is an AI model fault, not a cyber attack). No
`normalized` reading. Modal verbs as printed.

| Clause id | Source | PDF page | Printed page | Section | Modal |
|---|---|---|---|---|---|
| `uae.csc-ai-policy.2-4-2-redundancy-failover` | AI policy | 15 | 14 | 2.4 Operational Security, 2.4.2 (policy statement) | shall |
| `uae.csc-ai-policy.3-4-3-redundant-systems-ready` | AI policy | 36 | 35 | 3.4.3 Continuity Planning for AI/ML Systems (guidance) | should |
| `uae.csc-ai-policy.3-6-2-automated-response-human-intervention` | AI policy | 41 | 40 | 3.6.2 Incident Reporting and Management for AI/ML (guidance); two consecutive bullets, `[...]` skips only the bullet glyph | should |
| `uae.csc-isf.cii-sectors-cross-sector-sharing` | Information Sharing Framework | 32 | 31 | 3.1 National Level Entities, CII sectors, item 4 | none (a listed role) |
| `uae.csc-isf.traffic-light-protocol` | Information Sharing Framework | 24 | 23 | 2.2.3 Methods of Information Exchange, Traffic Light Protocol | none (descriptive) |
| `uae.csc-cirp.ncrg-level3-declaration` | Incident Response Plan | 18 | 17 | 2.2 NCRG, role during Significant Cyber Incidents (Level 3) | "is to" |
| `uae.csc-cirp.ncrg-sector-impact-information` | Incident Response Plan | 16 | 15 | 2.2 NCRG, Membership | "are expected to" |

`uae.csc-cirp.ncrg-sector-impact-information` was not in the human's list: the agent drafted it
as a further information_deadlock candidate (the human allowed "other passages if you find better
ones").

Each quote was cut from the extracted page text between start and end markers, so no character
was retyped; each is found on its cited page (`test_each_draft_quote_is_verbatim_on_its_page_...`).

## What would change if they were loaded (the brief)

Run against a temporary clause directory (the reviewed corpus plus these seven set to
`reviewed`; `test_loading_them_would_leave_the_diagnosis_goals_and_ranking_unchanged`):

- diagnosed failures, their causes, goals and findings: unchanged (only the clause-set label in
  each qualification names the temporary directory);
- repair ranking: unchanged;
- views: all seven would enter the `policy_legal_adviser`'s views only. As with NIST, that would
  change the adviser's LLM cache keys (gate-4 cache and preset answers would need re-recording),
  so loading stays a finals-backlog decision.

With the gap-examples route actually used (nothing loaded): gate-4 cache replays 36 of 36
(governed) and 72 of 72 (with `--governance off`) offline; the six preset cache keys are
unchanged (`PINNED_PRESET_KEYS`); `citation_map.py --check` and `build_reports.py --check` pass
unchanged; the technical report, citation map and golden tests pass; no knowledge-base rebuild
(not searched; `extracted_digest` is the same with or without their text on disk).

## Proposed gap_examples entries (gate 7; only after gate 1)

The report builder refuses an entry whose clause is not reviewed, so none is added yet. The
diagnosis and its qualification are not changed. Proposed lines:

**information_deadlock:network_incident_status->health_service_operator**
- `uae.csc-isf.cii-sectors-cross-sector-sharing`: "UAE cybersecurity information-sharing
  framework (CII sectors; binding unknown for this scenario): lists sharing a sector regulator's
  or sector incident response centre's information with other sectors as a role of CII sectors.
  It covers cybersecurity information between sectors; it does not say that a telecom operator
  shares a network incident's status directly with a health operator, or what may be shared."
- `uae.csc-isf.traffic-light-protocol`: "UAE cybersecurity information-sharing framework
  (descriptive): the Traffic Light Protocol marks in advance with whom shared information may be
  passed on. It illustrates a pre-agreed rule on what may be shared and with whom; it does not
  create a duty to share."
- `uae.csc-cirp.ncrg-sector-impact-information`: "UAE cyber incident response plan: sector
  representatives on the national cyber response group are expected to provide information on an
  incident's impact on their sector. It applies once a Significant Cyber Incident (Level 3) is
  declared; it does not cover an undeclared incident or an AI model fault."

**orphan_duty:activate_fallback_channel**
- `uae.csc-ai-policy.2-4-2-redundancy-failover`: "UAE AI cyber security policy (federal and CII
  entities; binding unknown for this scenario): states that the entity \"shall\" ensure
  redundancy and failover in its AI/ML systems. It covers a fallback within each entity; it does
  not say who activates one across the telecom-health boundary."
- `uae.csc-ai-policy.3-4-3-redundant-systems-ready`: "UAE AI cyber security policy guidance
  (\"should\"): redundant systems or alternative processes ready for immediate deployment where
  AI/ML systems are critical to operations. It illustrates a ready fallback; it does not name who
  decides to deploy it."

**undefined_trigger:review_automated_lockouts**
- `uae.csc-ai-policy.3-6-2-automated-response-human-intervention`: "UAE AI cyber security policy
  guidance (\"should\"): automated responses based on predefined conditions and incident severity
  levels. It illustrates a trigger set in advance; it concerns AI/ML security incidents (attacks),
  not a model fault, and sets no threshold for reviewing an automated lockout."

**orphan_duty:reverse_automated_lockouts**
- `uae.csc-ai-policy.3-6-2-automated-response-human-intervention`: "UAE AI cyber security policy
  guidance (\"should\"): a fail-safe that allows timely and informed human intervention where
  automated responses may not be suitable. It illustrates a human override of an automated
  response; it does not assign who intervenes."

**No entry proposed:** `uae.csc-cirp.ncrg-level3-declaration` (the NCRG Chair declares Level 3 when
alert-schema thresholds are met, on the NSOC's recommendation). It is context for escalation of
national cyber incidents; no diagnosed failure is about that escalation, so it maps to none.

## Open for the human

- Gate 1: check the seven quotes against the PDFs (pages above).
- Gate 7: the proposed entries and relevance lines above.
- Gate 6: AGENTS.md says "the 24 original PDF documents in `policies/sources/`" and lists what is
  never committed (".env, data/, secrets, or the two published books"). With three local-only
  PDFs, a proposed wording: "...the 24 original PDF documents in `policies/sources/` (plus three
  UAE Cyber Security Council PDFs kept locally only, not redistributed: see `NOT_REDISTRIBUTED`)"
  and add "or the not-redistributed sources" to the never-commit list. Not edited.
