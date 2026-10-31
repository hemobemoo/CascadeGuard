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
