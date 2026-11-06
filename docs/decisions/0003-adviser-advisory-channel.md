# ADR 0003 — The Policy Adviser's answers are a separate advisory channel

Status: **decided (human, Ibrahim Melhem, 2026-11-05)**. Branch `phase-7-adviser-query`.

## Context

"Ask the Policy Adviser" (`agents/adviser_query.py`, CLI `cascadeguard ask`, UI panel under the
timeline) lets a judge pause at a step T+n and ask the `policy_legal_adviser` a question. In LLM
mode the model returns an `AdviserPayload` (the seven answer sections), not an `AgentDecision`.
AGENTS.md says agents may only return an `AgentDecision`. The phase-auditor raised this as a
gate-8 question.

## Decision

The adviser's answer is accepted as a separate advisory channel, on these conditions:

1. **Read-only.** It never changes simulation state and is never seen by agents or by the
   engine's decisions. It reads the adviser's own boundary-filtered `RoleView` at T+n of the
   governed scripted baseline; nothing it returns goes back into a run.
2. **No effect on results.** It never affects the goldens, the citation map, decision or
   citation counts, or the gap analysis. None of the modules that produce them imports it
   (`tests/unit/test_adviser_query.py::test_the_advisory_channel_reaches_no_result`).
3. **Citations validated before display**, the same as agent citations: every cited id must be
   one of the loaded clauses (reviewed or illustrative) retrieved for the question
   (`engine/adviser_check.py`, `unknown_citation`). Quotes, sources, pages and status labels
   come from the loaded clause, never from the model; an answer the check rejects is replaced
   by the deterministic template, with the reasons.
5. **Model text kept apart (option (b), human decision 2026-11-06).** The seven sections are
   always the engine's template text, built from the clauses the model chose; sections 1, 5 and
   6 never hold model text. Every line the model wrote is shown only in a separate block,
   "Model commentary (unverified agent statement)", after the seven sections, each line under
   the agent-statement label. The engine's phrase checks (gap, status, authority wording,
   control characters) still run on every commentary line. Reason: review round 3 showed that
   phrase lists cannot catch every wording, so the sections must not depend on them.
   **Amended 2026-11-06 (human decision, branch `adviser-commentary-check`):** the gap, status
   and authority checks run per sentence. A flagged sentence is withheld; the block shows the
   others and "N sentences withheld by the engine check" with the reasons (the withheld text is
   never shown). Two narrow allowances: an absence scoped to the evidence the model was given
   ("not identified in the provided evidence", "the retrieved clauses do not address"), and a
   part of the status label of the clause the sentence is about (e.g. "illustrative"; never the
   bare word "binding"; a sentence naming several clauses may use only the parts they share). An
   evidence-scoped sentence may not also speak about the law (any law, statute, country or
   "anywhere" word flags it), and a phrase split across a sentence end is checked on the joined
   run of the sentences still shown. Binding, permit, authorise and legal-gap claims are
   withheld when they match the engine's phrase lists; a phrase list cannot catch every
   paraphrase (test-breaker round 2: e.g. "carries full legal authority" was shown before it was
   added). **Decided by the human, 2026-11-06:** accept the residual risk; stop extending the
   phrase lists; one structural rule: a commentary sentence naming an illustrative clause
   (`illus.*`, including its relevance note) is withheld, and when the answer cites one the block
   shows "Illustrative clauses are synthetic rules written for this scenario, not UAE law."
   When every sentence is flagged, the answer keeps no commentary lines and says "All N
   sentences ... withheld" (no template fallback). **Known limit:** Model commentary is filtered by phrase lists and labelled unverified; it can still contain wording the filter does not catch. The answer itself (sections 1–7) is always the engine's text.
   Also withheld: a sentence naming a clause the sections do not show (so no status label would
   be shown for it; at most 3 UAE and 2 international clauses are shown), and a sentence with
   letters outside the Latin blocks (look-alikes). Each relevance line carries its clause's
   status label. Runs of up to 8 shown sentences, across lines in display order, are re-checked. The
   structure (citations, UAE/international split, responsible role, abstention, control
   characters) still rejects the whole answer. The prompt (adviser-v2) asks the model to say
   "not identified in the provided evidence". Trade-off: a withheld sentence can change how its
   neighbours read; every shown sentence stays an unverified agent statement after the engine's
   seven sections.
6. **CLI calls a model only with `--live`** (human decision 2026-11-06); the UI switch is
   unchanged (off by default, shown only with `OPENROUTER_API_KEY`, 20 live calls per browser).
4. **AGENTS.md** records the exception in one line (gate 6, approved with this decision).

## Alternatives not taken

- Wrapping the answer in an `AgentDecision`: the decision type carries proposed actions for the
  engine, which an advisory answer must never have.
- Deterministic template only: the human asked for LLM mode in the demo (brief of 2026-11-05).
