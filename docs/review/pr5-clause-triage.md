# PR 5 evidence triage: `scenarios/uae_health_access/gap_examples.yaml`

evidence-auditor, round 1 (HEAD 4771a65), on the draft mapping. No clause file changed in PR 5.
Every quote in `docs/gap-analysis.md` was found verbatim on its cited page (extracted text and
PDF; the Charter against its reviewed transcriptions). Every status label matches its clause.

| # | Failure -> clause | Round 1 | Action |
|---|---|---|---|
| 1 | information_deadlock -> `eu.gdpr.art33-1` | FIX (MAJOR): relevance dropped "where feasible" and the exception | Relevance reworded to the clause's own terms |
| 2 | information_deadlock -> `oecd.ai-principles.accountability-cooperation` | FIX (MINOR): dropped "as appropriate" and the risk-management framing | Relevance reworded |
| 3 | orphan_duty:reverse_automated_lockouts -> `oecd.ai-principles.robustness-override` | CLEAN | — |
| 4 | orphan_duty:reverse_automated_lockouts -> `unesco.ai-ethics.review-and-correct` | CLEAN | — |
| 5 | orphan_duty:reverse_automated_lockouts -> `uae.ai-charter.human-oversight` | CLEAN | — |
| 6 | orphan_duty:activate_fallback_channel -> `unesco.ai-ethics.responsibility-accountability` | NEEDS-HUMAN-JUDGMENT: accurate, weak fit | For the human (gate 7) |
| 7 | orphan_duty:activate_fallback_channel -> `uae.ai-charter.safety` | FIX (MAJOR): against the clause's note "Context for suspending the traffic-management model only" (human decision 4d) | Entry removed |
| 8 | undefined_trigger:review_automated_lockouts -> `unesco.ai-ethics.human-oversight` | NEEDS-HUMAN-JUDGMENT: states no trigger; addressed to Member States | For the human (gate 7) |
| 9 | undefined_trigger:review_automated_lockouts -> `uae.ai-charter.human-oversight` | NEEDS-HUMAN-JUDGMENT: no trigger; also the loaded safeguard on this action | For the human (gate 7) |

Other round-1 findings: QUESTION-FOR-HUMAN on the undefined-trigger section (the Charter
safeguard on `review_automated_lockouts` is loaded but listed only as an example): the section
now also lists "Other loaded clauses on this action (not counted by the diagnosis)", stated as
fact; whether it counts as a trigger is the human's call. MINORs fixed: the examples heading, the
"binding basis" wording scoped to the loaded clause set, the qualification on the live-LLM
bullets, the stale inventory note. Deferred: the engine's diagnosis text "No clause triggers ..."
(engine wording; the qualification follows it on the next line).

## Round 2 (HEAD 76d9eb6)

All round-1 FIXes resolved; quotes, pages and labels verified again. New: MINOR FIX on entry 3
(`oecd.ai-principles.robustness-override`: "as appropriate" and "risks causing" restored) and
MINOR wording on entries 1 (GDPR: "not later than 72 hours after becoming aware of it") and 6
(UNESCO para 43: "Appropriate"); all three applied. QUESTION-FOR-HUMAN on entry 1: the fit of a
personal-data-breach notice to a supervisory authority with a cross-organisation share of network
status; and, on entry 6, the clause's own note gives its use as tracing the lockouts to the
traffic model, not activating a fallback channel. Both for the human (gate 7).

## Round 3 (HEAD ac97aad): PASS

Round-2 fixes for entries 1, 3 and 6 confirmed against the clause texts; all quotes, pages and
labels verified again. No BLOCKER or MAJOR. Optional MINORs applied: entry 4 reworded to the
clause's terms ("submissions", "rights and freedoms") and entries 4 and 7 tagged "(a non-binding
recommendation)" like the others. Open for the human (gate 7): entries 1, 6, 7 and 8 (fit), and
whether the Charter safeguard listed under "Other loaded clauses on this action" counts as a
trigger.

| # | Failure -> clause | Round 3 |
|---|---|---|
| 1 | information_deadlock -> `eu.gdpr.art33-1` | NEEDS-HUMAN-JUDGMENT (fit) |
| 2 | information_deadlock -> `oecd.ai-principles.accountability-cooperation` | CLEAN |
| 3 | orphan_duty:reverse_automated_lockouts -> `oecd.ai-principles.robustness-override` | CLEAN |
| 4 | orphan_duty:reverse_automated_lockouts -> `unesco.ai-ethics.review-and-correct` | CLEAN |
| 5 | orphan_duty:reverse_automated_lockouts -> `uae.ai-charter.human-oversight` | CLEAN |
| 6 | orphan_duty:activate_fallback_channel -> `unesco.ai-ethics.responsibility-accountability` | NEEDS-HUMAN-JUDGMENT (fit) |
| 7 | undefined_trigger:review_automated_lockouts -> `unesco.ai-ethics.human-oversight` | NEEDS-HUMAN-JUDGMENT (no trigger) |
| 8 | undefined_trigger:review_automated_lockouts -> `uae.ai-charter.human-oversight` | NEEDS-HUMAN-JUDGMENT (no trigger) |

## Gate 7: human decision (2026-10-31, Ibrahim Melhem)

| # | Failure -> clause | Decision | Reason (human) |
|---|---|---|---|
| 1 | information_deadlock -> `eu.gdpr.art33-1` | **Rejected, removed** | A personal-data breach notice to a regulator is a different duty from an operational status share between operators; foreign and not binding, so it adds risk and no evidence. |
| 2 | information_deadlock -> `oecd.ai-principles.accountability-cooperation` | **Approved** | CLEAN; the only example for the information deadlock. |
| 3 | orphan_duty:reverse_automated_lockouts -> `oecd.ai-principles.robustness-override` | **Approved** | CLEAN |
| 4 | orphan_duty:reverse_automated_lockouts -> `unesco.ai-ethics.review-and-correct` | **Approved** | CLEAN |
| 5 | orphan_duty:reverse_automated_lockouts -> `uae.ai-charter.human-oversight` | **Approved** | CLEAN |
| 6 | orphan_duty:activate_fallback_channel -> `unesco.ai-ethics.responsibility-accountability` | **Rejected, removed** | The clause's own note limits its use to tracing the lockouts to the traffic model (same reasoning as decision 4d). |
| 7 | undefined_trigger:review_automated_lockouts -> `unesco.ai-ethics.human-oversight` | **Approved with rewording** | It fits because it states no trigger: the relevance line now says it sets no condition or threshold for review. |
| 8 | undefined_trigger:review_automated_lockouts -> `uae.ai-charter.human-oversight` | **Approved with rewording** | As 7. |

`gap_examples.yaml` is now `status: reviewed`, `reviewed_by: Ibrahim Melhem`, `reviewed_on:
2026-10-31` (the validator requires all three once every entry is approved). After the two
removals `orphan_duty:activate_fallback_channel` has no example: its section says "No reviewed
example clause is mapped to this failure" (tested).

Reviewer questions: Q1, the Charter safeguard on `review_automated_lockouts` is **not** a trigger
(no condition, threshold or time; not binding); it stays under "Other loaded clauses on this
action" and `undefined_trigger:review_automated_lockouts` stands. Q2, the live section must state
the repair result itself, not only point to it (done). Q3, the draft stays off `main` until the
human approves its wording; after approval it may land unlinked.
