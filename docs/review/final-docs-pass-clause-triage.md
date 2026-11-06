# Final docs pass (PR #39): evidence triage

Evidence-auditor verdict: **PASS** (2026-11-07). No clause, policy, scenario, report or
evaluation file changed, so no clause was re-audited this round. The audit checked the new
diagram nodes and edges against the imports and calls in `src/cascadeguard/`, and the added text.

| item | result | evidence |
|---|---|---|
| node Policy Adviser (Q&A), `agents/adviser_query.py` | CLEAN | file exists |
| node Adviser answer check, `engine/adviser_check.py` | CLEAN | file exists |
| rename Vector index to Knowledge-base search | CLEAN | kb.py `search_kb` (hybrid), `search_kb_keyword` |
| `cli --> adviser` (ask) | CLEAN | cli.py:22 import, cli.py:870 `aq.ask` |
| `app --> adviser` (adviser panel) | CLEAN | app.py:32 import, app.py:1337 `aq.ask` |
| RoleView edge | FIX, applied | the adviser only imports the `RoleView` type (adviser_query.py:69); the view is built in the baseline and passed in (cli.py:765-767), so the edge now runs `bound --> adviser` |
| `adviser --> kb` (hybrid or keyword search) | CLEAN | adviser_query.py:261-269 |
| `adviser -.-> llm` (optional model commentary) | CLEAN | `_strict`, `_content` on the model path only |
| `adviser -.-> acheck` (checks model answer) | CLEAN | `check_answer` in `llm_answer`, adviser_query.py:778 |
| missing `adviser --> cache` | FIX, applied | `canonical_view`, adviser_query.py:43, 423-424 |
| missing `adviser --> pol` | FIX, applied | `PolicyClause`, `is_uae_jurisdiction`, adviser_query.py:51 |
| missing `adviser -.-> cons` | FIX, applied | `agent_statement`, adviser_query.py:65, 869 (model path) |
| missing `acheck --> pol`, `acheck --> cons` | FIX, applied | adviser_check.py:51-52 |
| labels `app --> cli`, `cli -.-> kb` incomplete | FIX, applied | app.py `adviser_asker`; cli.py:775-776 `committed_index()` |
| solid vs dotted for entry edges | FIX, applied | legend now says a command's or the UI panel's entry edge is solid |
| kb.py docstring "LLM context path only" is stale | deferred (MINOR) | kb.py must stay unchanged in this PR |
| step b narration, README, PROGRESS text | CLEAN | no legal, gap or status-label claims |
