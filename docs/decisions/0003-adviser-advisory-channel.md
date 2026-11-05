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
   come from the loaded clause, never from the model; every model-written line is shown under
   the agent-statement label; an answer the check rejects is replaced by the deterministic
   template, with the reasons.
4. **AGENTS.md** records the exception in one line (gate 6, approved with this decision).

## Alternatives not taken

- Wrapping the answer in an `AgentDecision`: the decision type carries proposed actions for the
  engine, which an advisory answer must never have.
- Deterministic template only: the human asked for LLM mode in the demo (brief of 2026-11-05).
