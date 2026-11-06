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
| labels `app --> cli`, `cli -.-> kb` incomplete | FIX, applied | app.py `adviser_asker`; cli.py:774 `committed_index()`, cli.py:776 `StoredQueries` |
| solid vs dotted for entry edges | FIX, applied | legend now says a command's or the UI panel's entry edge is solid |
| kb.py docstring "LLM context path only" is stale | deferred (MINOR) | kb.py must stay unchanged in this PR |
| step b narration, README, PROGRESS text | CLEAN | no legal, gap or status-label claims |

## Round 2 (evidence-auditor PASS, 2026-11-07)

Every round-1 fix CONFIRMED (`bound --> adviser`: orchestrator.py:196 builds each role's view;
cli.py:765-767 and app.py:671 pass the adviser's in). Three MINORs: two fixed, one left as the auditor allowed:

| item | result | evidence |
|---|---|---|
| `cli -.-> kb` "index for ask" dotted, though every `ask` loads the index | FIX, applied | cli.py:774 in `adviser_asker`; split into solid `cli -->|index for ask| kb` and dotted `cli -.->|kb query, kb export| kb` |
| adviser uses adviser_check wording constants on every path | not drawn (optional per the auditor) | `NOT_IDENTIFIED`, `NOT_ESTABLISHED` in `template_answer` (adviser_query.py:463, 505, 522, 553). A second adviser/acheck edge was tried, but mermaid placed its label against the dotted edge's label in every direction; constants only, like the undrawn `CONTEXT_LABEL` and `PROJECT_ROOT` imports |
| this file: wrong line for `committed_index()`, round 2 missing | FIX, applied | corrected to cli.py:774; this section |
