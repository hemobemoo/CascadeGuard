# PROGRESS — CascadeGuard

Session hand-off. Read this before doing anything (see `AGENTS.md`).

## Current phase

**Phase 4 — Demo UI (branch `phase-4-ui`): built, review loop running.** The human approved
`specs/004-demo-ui.md` on 2026-10-24 (no pytest-asyncio: view-model tests plus a Playwright run
for the page; exports as browser downloads only) and the CascadeGuard.md section 6 wording
(fbc51e1). The full flow works in the browser with scripted agents (Playwright MCP run,
screenshots in `docs/review/phase-4-screens/`). Review round 2: evidence-auditor PASS,
test-breaker FAIL (no BLOCKER; one MAJOR, see "Waiting on human"), phase-auditor PASS.
Do not merge before the human has seen the screenshots.

## Done

### Phase 4 — Demo UI (branch `phase-4-ui`, not merged)
- `ui/app.py` (NiceGUI, port 8765 or `CASCADEGUARD_UI_PORT`): scenario picker, timeline, role
  views, dependency graph (`ui.echart`) with failures highlighted (click a failure or pick it),
  ranked and discarded repairs, baseline vs replay, JSON/Markdown downloads.
- `ui/view_model.py`: formatting only; labels come from the engine and `storage/export.py`.
- `RunResult.views` and `RunResult.boundaries` (display copies). UI and CLI share one Markdown
  export builder (`cli.baseline_markdown`, `cli.search_markdown`); all Markdown exports carry
  the disclaimer.
- Tests: `tests/unit/test_view_model.py` (labels, role views, graph highlight, byte-identical
  exports, port).

Verify:

```bash
uv run python -m cascadeguard.ui.app      # then open http://localhost:8765
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 3 — Repair and replay (branch `phase-3-repair`)
- `domain/repairs.py`: `RepairEdit` (five operation types, typed parameters only) and an
  immutable `RepairProposal` (tuples; canonical `repair_id`).
- `simulation/replay.py`: applies a repair as hypothetical rules (`repair.<edit id>`), trigger
  events and one boundary widening, reruns the identical incident, and compares
  (`ReplayComparison`: goals, failures no longer blocking / remaining / new, changed verdicts).
- `engine/repair_search.py`: candidates from diagnosed failures and restricted shares, hard
  filter (static and after replay), replay of every combination up to 2 edits, lexicographic
  ranking, `requires_authorization`.
- `storage/audit.py` (DuckDB, `--audit`), `storage/export.py` (JSON + Markdown, `--export`).
- CLI: `cascadeguard repairs <scenario>`; `cascadeguard run <scenario> --repair <id>`.
- Golden: `scenarios/uae_health_access/expected_repairs.yaml` (search + one successful and one
  unsuccessful replay, real clause set). Spec: `specs/003-repair-and-replay.md`.

Verify:

```bash
uv run cascadeguard repairs uae_health_access
uv run cascadeguard run uae_health_access --repair owner.reverse_automated_lockouts.health_service_operator+share.network_incident_status.telecom_operator.health_service_operator
uv run cascadeguard run uae_health_access --repair share.network_incident_status.telecom_operator.health_service_operator
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 0 — Tooling (merged, tag `phase-0`)
uv project on Python 3.12, Ruff, Pyright (strict), pytest, CLI stub, `.env.example`, `.gitignore`
(including the two books by filename), `README.md`.

### Phase 2 — Engine with scripted agents (merged, PR #3, tag `phase-2`)
- `simulation/state.py`, `boundaries.py`, `orchestrator.py`; `engine/constraints.py`,
  `graph.py` (NetworkX), `diagnosis.py`; `agents/base.py`, `scripted.py`; `domain/findings.py`.
- Scenario data: `roles.yaml` action preconditions, `scenario.yaml` recovery goals and
  `opens_obligations`, `scripted_decisions.yaml`.
- `cascadeguard run uae_health_access [--clauses DIR]` prints the clause set (with status labels),
  timeline, accepted/rejected actions, obligations, goals, findings and diagnosed failures.
- Golden: `tests/fixtures/uae_health_access/expected_baseline.yaml` (synthetic fixtures).
  Spec: `specs/002-engine-and-diagnosis.md`; `docs/architecture.md`.

Verify:

```bash
uv run cascadeguard run uae_health_access --clauses tests/fixtures/clauses   # fixture baseline
uv run cascadeguard run uae_health_access                                    # real clause set
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

### Phase 1 — Domain, policy extraction, and scenario
- **1a/1b Extraction + inventory:** `scripts/extract_pdf_text.py` → `policies/extracted/*.jsonl`
  and `_inventory.json`. Inventory table in `docs/policy-inventory.md`. Telecom Law pages 13–47
  have no extractable text (vector-outlined glyphs; OCR would be needed).
- **1c Domain:** `src/cascadeguard/domain/` (`base`, `policies`, `decisions`, `repairs`,
  `scenario`). Clause loader `src/cascadeguard/knowledge/loader.py`. Scenario loader
  `src/cascadeguard/simulation/loader.py`.
- **1d Scenario:** `scenarios/uae_health_access/` (`scenario.yaml`, `roles.yaml`, `README.md`).
- **1e Clauses:** 31 clauses in `policies/reviewed/*.yaml`: 29 `draft` (verbatim, verified against
  the extracted page by the tests) and 2 `illustrative`.
- Docs: `specs/001-domain-and-scenario.md`, `docs/policy-methodology.md`,
  `policies/reviewed/README.md`.

Verify:

```bash
uv sync
uv run python scripts/extract_pdf_text.py          # regenerates policies/extracted/ (slow: the books)
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest
```

## Decisions

- Repair grammar = the five types in `CascadeGuard.md` §6; lexicographic ranking as in `AGENTS.md`.
- CLI uses stdlib `argparse` (no new dependency). Pyright `strict`. Ruff excludes `*.md`.
- **Health-data regime (working reading of draft clauses, pending human review):** Federal Law
  No. 2 of 2019 is treated as applicable (Art. 2). The PDPL is not assumed to apply, because
  Art. 2(2)(e) excludes health data that has its own legislation. The scenario places the portal in
  Dubai, so the DHA Health Data Protection and Confidentiality Policy is treated as applicable.
- **Information model:** facts carry a data category, a holder and a certainty. A role's boundary
  lists the categories that may ever reach it. `define_minimum_data_share` widens a boundary by
  one category.
- **Verbatim check:** clause text must appear on its cited page, ignoring whitespace. `[...]` marks
  an omission (two-column layouts, footnote markers); the pieces must appear in order.
- `document_date` may be `unknown` when the PDF prints no date (it is never guessed).
- `page` is the PDF viewer page (1-based), the same index as `policies/extracted/`; not the printed page number.
- Scenario loading lives in `simulation/loader.py` (not listed in the structure file; it is the
  natural home, and Phase 2 builds the rest of `simulation/` around it).
- Dev dependency `types-pyyaml` (PyYAML type stubs for strict Pyright): **approved by the human**.
- Telecom (2026-10-22): the two telecom rules stay illustrative (human decision). Superseded in
  part: the human then supplied an OCR copy (see the Telecom Law OCR decision below).
- Breach-reporting period for health data: **stays unknown** (human decision); the PDPL Executive
  Regulations are not added. The unknown period is itself a candidate finding.
- `[...]` gaps: a test extracts the skipped text and fails on any qualifier, modal, number or
  cross-reference unless the gap is only a footnote marker or a margin requirement ID. FL 2/2019
  Art. 4 and PDPL Art. 2(2) are now quoted in full instead of with gaps.
- `PolicyClause.binding` and `page` are strict (no "yes"/1/"3" coercion), with tests
  (phase-auditor round 2).
- **`normalized` basis (human decision 5h, 2026-10-23):** `normalized` keeps its links to
  `roles.yaml` actions and records `basis: stated | interpreted`; `interpreted` needs a one-line
  `mapping_note` (the loader rejects it otherwise). A power to regulate is never read as an
  obligation to act (such a rule becomes illustrative). The engine treats both bases the same;
  reports and the UI must show `PolicyClause.status_label` (e.g. "draft (interpreted)").
  All 14 `normalized` blocks have a basis: 12 interpreted, the 2 illustrative ones stated.
- **Telecom Law OCR (human-supplied, 2026-10-22):** a derived source in
  `policies/sources/ocr/…ocr.pdf`, extracted to its own JSONL with `"ocr": true`; the original is
  unchanged (restored in 428e114 after 0a51f82 overwrote it). Quotes from OCR pages are
  corrected against the page image and must carry "OCR — check against image" in notes (loader
  check). Provenance and known OCR errors in `docs/policy-methodology.md`.
- **Telecom illustrative rules vs. Art 12, 13, 14(3), 30** (checked against page images): none
  states an operator incident-reporting duty or deadline, so `illus.telecom.incident-report` stays
  illustrative ("the Law delegates this to TDRA regulations / the Executive Order, which are not in
  the reviewed corpus"). Art 14(5) supports the regulator's information requests; drafted as
  `uae.telecom-law.art14-5` (`interpreted`). `illus.telecom.regulator-information-request` stays
  loaded until that draft is reviewed.
- Draft clauses are not loaded by the engine. Phase 2 may be built against synthetic fixture
  clauses under `tests/fixtures/` (AGENTS.md "Human gates"); fixtures never prove the real scenario.
- **Dubai Law No. 26 of 2015 is not drafted as a clause.** Art. 3 applies it to government
  entities and to "Persons ... who are determined by the Competent Entity"; nothing in the corpus
  shows the scenario's private operators are determined. It governs dissemination and exchange of
  "Dubai Data" through the Competent Entity's platform, not an incident channel between operators,
  and Art. 13(a) is without prejudice to data legislation in force; the agent's reading is that it
  does not override FL 2/2019 Art. 16 (not a legal conclusion). **Human agreed (2026-10-22):** not drafted; kept as a candidate note only.
- **"UAE Policy Foundation.pdf" (human decision, 2026-10-22):** the compilation's issuer is
  "not printed (unofficial compilation)", date unknown. Clauses from its Charter part (pp. 1–3:
  `uae.ai-charter.safety`, `uae.ai-charter.human-oversight`) use issuer "UAE Artificial
  Intelligence, Digital Economy and Remote Work Applications Office", date 2024-07, binding false.
  The other parts and their pages are listed in `docs/policy-inventory.md`.

- **Phase 2 engine decisions (2026-10-23):** authority comes from an obligation or permission
  clause that is binding, or from an illustrative scenario rule (`binding: false`).
  `binding: unknown` gives only "authority uncertain"; non-binding guidance never gives
  authority. A citation of an unloaded clause rejects the whole decision (`draft_citation` or
  `unknown_citation`, both findings). All roles decide on the same snapshot; the engine applies
  decisions in `roles.yaml` order. Mandate overlap is not detected yet; it needs reviewed
  DHA/PDPL clauses.
- **Phase 2 review round 3 (2026-10-23, last round):** phase-auditor FAIL only on question 7o
  (no code change); test-breaker FAIL (BLOCKERs: inject text and decision points still told each
  recipient about the other organisation; a misspelt request category dodged a prohibition;
  MAJOR: clause data categories unchecked). Fixed after the round, not re-reviewed: decision
  points name one role and go only to it; inject descriptions hold only what all recipients may
  know; request and clause categories must be scenario categories (`unknown_data_category`);
  empty impostor decisions are findings; the summary lists every fact delivery and goal minute.
  Each fix has a test, mutation-checked against the old text.
- **Phase 2 review round 2 fixes (2026-10-23):** decisions re-validated from plain data
  (constructed objects and subclassed containers rejected or normalised); a share delivers
  exactly the fact it checked; no fact is released before its inject; every bad citation is a
  finding; self-targeted shares rejected; only obligation clauses open obligations, and
  `binding: unknown` ones are marked uncertain; book names refused case-insensitively and
  `source_file` must resolve inside `policies/sources`; stray files, subdirectories, extra keys
  and blank text refused; every clause id in the CLI carries its status label; fresh-process
  determinism test with three hash seeds. Requests for a category outside the requester's own
  boundary stay accepted (documented in the spec).
- **Phase 2 review round 1 fixes (2026-10-23):** inject text, decision points and clauses go only
  to the inject's recipients; views hold deep copies of facts and the state keeps private
  copies; prohibitions apply to every action kind (requests by category included); a safeguard
  without a data category is a protective duty, never a ban (engine decision, recorded in the
  spec); citations are checked before any early return; wrong role/time is a finding logged
  under the real role; obligations on `any` are fulfilled by whoever acts; only firm clauses
  are triggers. The golden summary now lists every decision-level rejection and each finding's
  minute and role (format change only, same content).
- **Phase 2 fixtures:** synthetic illustrative clauses in `tests/fixtures/clauses` reuse the draft
  clause ids and behave in the engine as those clauses would: same `normalized` reading and same
  authority/trigger outcome (binding true -> illustrative scenario rule; binding unknown kept;
  non-binding guidance carries no `normalized`). `tests/unit/test_fixtures.py` fails on drift. They are labelled "SYNTHETIC FIXTURES ... not the real corpus" in
  every output. The real-corpus golden `scenarios/uae_health_access/expected_baseline.yaml`
  was added in 392f162 after the core-set review.
- **NetworkX without stubs:** `types-networkx` is not on the AGENTS.md list, so NetworkX is
  confined to `engine/graph.py` behind typed helpers instead of adding a dependency.
- **Human decisions, 2026-10-23 (answers to "Waiting on human"):**
  - Core set **reviewed** (`status: reviewed`, commit "Reviewed by human: ..."):
    `uae.fl2-2019.art2`, `uae.pdpl.art2-2`, `uae.fl2-2019.art4`, `uae.fl2-2019.art16`,
    `uae.fl2-2019.art6`, `dha.pp11.4-18-2`, `dha.pp11.4-18-4`, `dha.pp11.4-18-1`,
    `uae.ai-charter.human-oversight`. The two telecom rules stay illustrative. The human's
    changes below were applied to these clauses before they were marked reviewed.
  - Commit 194103a confirmed: the rule changes, including auto-merge, are the approved ones.
  - 7o: the fixture-based golden is accepted for Phase 2, labelled synthetic; the real-corpus
    golden is added after the core-set review.
  - 7n: a citation must concern the citing role or its action; a mismatch rejects the decision
    and is a finding.
  - 7q: no separate process; frozen read-only views suffice for this slice (known limit).
  - 7r: reject legal-gap claims made without citations.
  - 7s: mandate-overlap detection waits for reviewed DHA and PDPL clauses; never inferred from
    fixtures.
  - 7t/7v: Art 4 and Art 16 are conditional prohibitions, not a flat ban. Where a permission or
    exception depends on conditions the engine cannot evaluate, the result is "authority
    uncertain - requires determination"; the engine never decides a condition is met.
  - 7u: `binding: unknown` on illustrative clauses is for fixtures only; a test keeps real
    clauses from it unless a human sets it.
  - 7m: a power to issue rules on requesting information is not a permission to request it in
    this incident; `uae.telecom-law.art14-5` stays interpreted with "authority uncertain"; the
    illustrative rule stays loaded.
  - h2: `dha.pp11.4-18-1` supports "a fallback plan must exist" (`maintain_fallback_plan`), not
    authority to activate it; activation authority is uncertain. `dha.pp11.4-18-5` models DHA
    only; the UAE Information Office is out of scope for this slice.
  - 7l: the human contacts GitHub Support about `refs/pull/1/head`; done for now.
  - Phase 2 round-3 fixes: no fourth review round; they are covered by tests but not
    re-reviewed, and the Phase 3 review loop covers them.
  - README: one line on source ownership with a link to each official source (added).

- **Human decisions, 2026-10-23 (second set):**
  - PR #3 merged; `main` tagged `phase-2`; Phase 3 started.
  - The post-review edit to `dha.pp11.4-18-1` stays; the edits in 9b7b7fa are accepted.
  - New gate-1 rule (rule-file change approved by the human): any edit to a `status: reviewed`
    clause sets it back to `draft` in the same commit and lists it for re-approval.
    `policies/approvals.yaml` holds the approved digest of each reviewed clause (baseline: the
    core set with the 9b7b7fa edits); `tests/unit/test_approvals.py` enforces the rule.
  - 3w: keep quoting the 2024 text. Checked on EUR-Lex (2026-10-23): Regulation (EU)
    2026/1744 (Digital Omnibus on AI, 8 July 2026, applies from 27 July 2026) amends
    Regulations 2024/1689, 2018/1139 and 2023/1230. It does not amend AI Act Art 14 or Art 73
    (it inserts Art 75(1a), a derogation from Art 73 for providers under the AI Office's
    competence), and it does not amend the GDPR, for which EUR-Lex lists only corrigenda (two
    amendment proposals, 52025PC0501 and 52025PC0837, are pending). All five `eu.*` clauses
    carry a dated "unchanged by the 2026 amendment" note; none was changed in substance.
  - 3x: the README note stays; no clause quotes `AIGuide_EN_v1-online.pdf` (inventory note).
  - Remaining open questions are collected for the end of Phase 3; none blocks it.
  - The 20 drafts stay draft; the human is told only if a Phase 3 repair needs one (none does).
- **Phase 3 engine decisions (2026-10-23):** a minimum data share widens the recipient's boundary
  (the Phase 1 information model), so it works the same whoever sends; candidates name the
  category's original holder. Search combines up to 2 edits. Repair rules are illustrative
  clauses labelled "hypothetical repair rule (not a source clause)". A failure "no longer
  blocking" may be gone only because its goal is met another way. `LogEntry.data_category`
  records the category a share or request touched (not in the golden summaries).

- **Phase 3 review round 1 (2026-10-23).** evidence-auditor PASS (MINORs fixed: EUR-Lex URL in
  the five EU notes, OECD truncation note, CLI wording, scripted uncertainty). phase-auditor FAIL
  (MAJOR: replay judgement outside `engine/`; JSON exports without labels/qualifications).
  test-breaker FAIL (BLOCKERs in Phase 2 code: 7n scope widened by disallowed actions; 7r narrow
  regex and no qualification check; MAJORs: share filter only for the named sender, share
  authorization ignored roles/conditions, repair rules citable in replays, search output lost
  labels when nothing ranked). All fixed with tests, each mutation-checked:
  `ReplayComparison` moved to `engine/repair_search.py`; scope uses allowed actions only; gap
  claims need a citation and a qualification (`unqualified_gap_claim`); citations must be corpus
  clauses; share edits checked for every sender and new restricted-category deliveries discard a
  repair; `SearchResult` carries the clause set and labels; JSON exports label every clause and
  keep qualifications; repair ids include trigger and deadline; proposals re-validated in replay;
  ScriptedAgent returns copies; `document_date` must be a real date; audit `repairs` table.
  The scripted telecom T+30 uncertainty "No clause found that authorises this share." was removed
  (an uncited gap-style line; it never appeared in a golden). Expected-repairs golden regenerated:
  only repair ids (trigger/deadline suffix) and the sorted order of one discard's clauses changed.
- **Phase 3 review round 2 (2026-10-23).** phase-auditor PASS (QUESTION-FOR-HUMAN items only:
  4a-4c; MINORs fixed: rule text, stale PROGRESS line). test-breaker FAIL: BLOCKERs (share
  authorization checked only the named sender although the widened boundary lets any role
  send; gap claims could pass with a negated qualifier or a paraphrase), MAJOR (decision
  requester `action`/`counterpart` unchecked), MINORs (non-strict deadline, decisions mutable
  between collection and processing, weak identity and patient-record tests). All fixed with
  tests, each mutation-checked: a share needs a reviewed basis for every possible sender; gap
  claims only in the structured `AgentDecision.gap_claims` (citations + fixed qualification;
  free-text gap wording rejected; `overstated_gap_claim`); requester parameters checked;
  `deadline_minutes` strict; the orchestrator copies each decision on return; identity test
  compares fact releases both ways and every agent view, for both golden repairs. Two tests
  changed on purpose with the rule: cited free-text gap analysis is now rejected (use a
  GapClaim), and a reviewed share clause naming only one sender no longer exempts a share.
  `RepairProposal.requires_authorization` is computed by the engine (`proposal()`); replay
  does not use it.
- **Phase 3 review round 3 (2026-10-23, last round).** test-breaker FAIL: BLOCKER, an agent
  could still state a legal gap in free text with wording the gap pattern misses ("UAE law
  lacks any provision ...", "the legislation is entirely mute ...") and it was stored unlabelled
  in the log and audit store; MINOR, a decision-requester repair was never marked
  requires_authorization even if requesting needed authority. Fixed after the round, not
  re-reviewed: agent rationales are stored only under the fixed label "agent statement
  (unverified; not a finding or a legal conclusion)"; only GapClaims become candidate findings;
  the requester goes through the same authority check. Mutation-checked. Remaining
  QUESTION-FOR-HUMAN items: 4a, 4b, and new 4e (new conflicts do not lower the rank).
- **Human decisions, 2026-10-24 (answers to "Waiting on human" items 3-5):**
  - **5 (round-3 gate): approach accepted.** Gaps are stated only as structured GapClaims; all
    agent free text is labelled "agent statement (unverified; not a finding or a legal
    conclusion)". No attempt to catch every wording. One final test-breaker pass, limited to
    a4b5c82 and every place agent free text is stored, exported or printed; no further rounds.
    The Phase 4 spec (`specs/004-demo-ui.md`) requires the UI to show the same label.
  - **4c:** the gate-1 rule in AGENTS.md (8333dfa) is approved.
  - **Ranking (4a, 4b, 4e)**, `CascadeGuard.md` section 6 authoritative; ADR
    `docs/decisions/0001-repair-ranking.md`, AGENTS.md and `specs/003-repair-and-replay.md`:
    hard filters; clean repairs above repairs with new conflicts; within each group most
    critical blockers removed, fewest edits, fewest roles touched, fewest clauses cited; among
    repairs with new conflicts, fewest new conflicts. Agent choice: "not requiring
    authorization" and `repair_id` stay as the last tie-breaks (the human's order does not
    place the authorization tie-break). 4a: a blocker counts as removed only when its cause is
    gone; one hidden by its goal being met another way is "masked (goal met another way)".
    4e: repairs with new conflicts are ranked lower, never discarded; a conflict that is only a
    repair duty no scripted agent attempts is tagged `scripted_agent_limit` (revisit in
    Phase 5). `expected_repairs.yaml` regenerated.
  - **4d (draft mappings, clauses stay draft):** `mocai.ethics.fallback-plan` maps to
    `maintain_fallback_plan` (consistent with h2); `itu.y3172.req-ml-mng-003` has no action
    mapping (design requirement; standards and gap-analysis context); `uae.ai-charter.safety`
    has no permission mapping (non-binding principle); `uae.telecom-law.art14-5` mapping note
    rewritten to match 7m. `dha.pp11.4-18-5`: see 3p. `dha.pp11.applicability` keeps
    `binding: unknown` (3e).
  - **Evidence questions (working readings only, never legal conclusions):**
    3a protective reading: lock records linked to a health service account are treated as
    health data under FL 2/2019 Art 4 (basis interpreted), which keeps the Art 4/16 discard. The
    reviewed Art 4 clause already maps that share as interpreted; its note still says the
    question is for the human. It was **not edited**, because any edit sends a reviewed clause
    back to draft (gate 1) and the engine would drop it; update the note at its next
    re-approval. 3b: the portal operator is not assumed to be a "Health Authority"; the human
    checks the Arabic. 3c: FL 2/2019 is treated as the health data's own legislation; scenario
    assumption added to `scenarios/uae_health_access/README.md` (synthetic, non-governmental,
    DHA-licensed operator; exclusion (b) out of scope). 3d: "treated as applicable (working
    reading)" stays. 3e: `binding: unknown` stays. 3f: precedence "requires determination"; the
    unknown reporting period stays a candidate finding. 3j: the inventory may list filenames,
    page counts and title/author metadata only, never text. 3k: structure file updated.
  - **3i (DHA footers):** the extracted footers read "1/52" to "50/52" on viewer pages 1-50,
    one-to-one, with no missing or repeated number inside the copy. Footers 51/52 and 52/52 are
    missing: the copy ends on page 50 in section 5 (references, item 5.23). The drafted DHA
    clauses are on pages 1, 30, 31 and 32; none is next to the gap. The human looks for a
    complete copy.
  - **CI:** `.github/workflows/checks.yml` runs `uv sync --locked` and the full check command
    (actions/checkout, astral-sh/setup-uv; not a project dependency).
- **Final test-breaker pass (2026-10-24, FAIL), fixed after the pass, not re-reviewed:**
  BLOCKER: `ProposedAction.target` was free text for every action except share/request, and
  was stored and printed unlabelled (a gap could be stated there with no citation). MAJORs:
  unknown `action_type`, unknown share/request target, impostor `role_id` and the class name of
  a non-decision object were echoed unlabelled into the log, findings, DuckDB, JSON and CLI;
  `GapClaim.statement` became a finding without the label, and a newline in it forged a CLI
  line; the JSON export dropped a candidate gap claim's qualification. MINOR: unknown
  `data_category` echoed. Fixes: a target must be a role id for every action
  (`unknown_target` otherwise); agent strings that are not scenario ids are logged as
  `<not a scenario id; agent text withheld>`; malformed-type, unknown-target and
  unknown-category details are fixed text; rationale and gap statements are stored as
  `agent_statement(...)` (label, one line); the run JSON export adds `detail` to every finding
  and `qualification` to every candidate gap claim. `tests/unit/test_phase3_final_pass.py`
  (10 tests) fails on the old code and passes now. Not fixed (not in the human's scope, see
  "Waiting on human" 6): the OVERSTATED wording list, and `copy.deepcopy` running on agent
  output before the type check.
- **Human decisions, 2026-10-24 (follow-up to the final pass):**
  - **Ranking, two keys added** (ADR 0001, AGENTS.md, spec 003): hard filters; clean before
    new conflict; resolved (every critical goal met in the replay) before partial, then most
    critical goals met; most critical blockers removed at their cause; fewest critical
    blockers only masked; fewest edits; fewest roles; fewest clauses cited; not requiring
    authorization; `repair_id`. Among repairs with a new conflict, fewest new conflicts still
    breaks the ties left after clauses cited. Why resolved outranks blockers removed: the aim
    is a feasible recovery path, and masked blockers stay visible as findings.
    `expected_repairs.yaml` regenerated; owner + share is rank 1 again.
  - **3p: not applied.** The two clauses stay separate; the draft `dha.pp11.4-18-5` notes that
    its actor comes from 4.18.4. 3p is now part of the human's clause review.
  - **3a:** the reviewed Art 4 clause is not edited.
  - **Outside the pass scope, fixed with a test each:** OVERSTATED now also catches
    "conclusively", "definitely", "absolutely" (no further words: the label and the fixed
    qualification are the real safeguard); the orchestrator checks the type of agent output
    before deep-copying it (anything else goes to the engine uncopied and is rejected as
    malformed).
- **`RepairProposal` shape (Phase 3 decision).** `operation`/`applies_to`/`parameters` became
  `edits: tuple[RepairEdit, ...]`, because the ranking counts repair edits and a repair can need
  two (CascadeGuard.md section 6, "Repair 2"). Each edit keeps one closed operation type with
  typed parameters.

- **Phase 4 review round 1 (2026-10-24), test-breaker on 5747e23, f6ea214, 4f56dbe: FAIL.**
  BLOCKER: a cited clause id outside the corpus (decision or GapClaim citation) was stored and
  printed verbatim, so invented text and a forged CLI line reached every output. Fixed: such
  ids are shown as `<not a scenario id; agent text withheld>` everywhere (the existing test for
  unknown citations now expects that placeholder instead of the invented id, a deliberate rule
  change). MINORs fixed: `agent_statement` replaces control and format characters (terminal
  escapes, zero-width and bidi marks); the orchestrator rebuilds each decision from JSON
  instead of deep-copying, so a foreign object inside a `model_construct` decision runs no
  code; a test pins "not requiring authorization" after clauses cited. MINOR not fixed (human
  decision: no further words): OVERSTATED is a word list and is bypassed by homoglyphs or
  synonyms; the label and fixed qualification remain the safeguard.

- **Phase 4 human decisions (2026-10-24):** spec 004 approved as written; no pytest-asyncio;
  exports as browser downloads only (the CLI `--export` writes to disk); CascadeGuard.md
  section 6 sentence replaced with the human's wording (fbc51e1, own commit); README gives the
  port and `CASCADEGUARD_UI_PORT`; the next test-breaker round covers 0e76c21 first (done in
  round 2: the WITHHELD and control-character fixes hold).
- **Phase 4 review round 2 (2026-10-24).** evidence-auditor PASS (triage in
  `docs/review/phase-4-clause-triage.md`). test-breaker FAIL: MAJOR, no repeatable test proves
  the browser flow (human gate, below); MINORs fixed with tests: `_copy` now checks every nested
  value for an exact plain type before serialising (a `model_serializer`, generator, custom
  `__getattribute__`, custom tzinfo or `str` subclass runs no code and is rejected as
  malformed); UI and CLI Markdown exports are byte-identical (shared builder; test compares the
  CLI's files); the graph highlights only the selected failure, and only edges touching its
  subject (test checks a second failure's nodes are not highlighted); failures in the list are
  clickable; the banner shows the clause set. Reviewer QUESTION about AGENTS.md not matching
  the ranking: disagreement, AGENTS.md lines 46-60 already hold the human-approved order
  (f6ea214). Stale PROGRESS.md: fixed here.

- **Phase 4 review round 2, phase-auditor: PASS.** All four "Done when" items proven (it ran
  the flow itself in headless Edge on a clean export of 1e7fc22). MINORs fixed: the structure
  file lists `ui/view_model.py` (replacing the planned timeline/graph_view/replay_view modules)
  and `.claude/launch.json`; the masked, removed and requires-authorization labels are
  constants in `engine/repair_search.py` used by the CLI and the UI; the UI binds to
  127.0.0.1 only; the baseline runs off the event loop. QUESTION-FOR-HUMAN items: confirm the
  CascadeGuard.md section 6 approval in the PR, and approve or drop `.claude/launch.json`.

## Approved gate-5 exceptions

- **2026-10-22, book history purge (one time, approved by the human in chat).** Both book PDFs were
  copied to `C:\AI for Good Lab Hackathon UAE\CascadeGuard-book-backup\` (with a full
  pre-purge `git bundle` of all refs). History was rewritten with
  `uvx git-filter-repo --force --invert-paths --path-glob "*Abhivardhan*" --path-glob "*Oxford Handbook*"`
  (`--force` because this is a working clone, not a fresh one). `phase-1-domain-scenario` already
  sat on the rewritten `main` (no rebase needed); tag `phase-0` points at the rewritten Phase 0
  merge `51191ce`; branch `phase-0-tooling` deleted locally and on GitHub; `main`,
  `phase-1-domain-scenario` and `phase-0` force-pushed. `git log --all -- "*Abhivardhan*" "*Oxford*"`
  returns nothing; PR #2 head is the rewritten `d49da75`. The books stay on disk in
  `policies/sources/` (ignored). **Residual:** GitHub keeps the read-only ref `refs/pull/1/head`
  at the old commit `9f67523`, whose ancestors still contain the books; only GitHub Support can
  remove it. Other clones made before 2026-10-22 must be re-cloned.

## Minimal core set for Phase 2

The engine needs these reviewed (or confirmed illustrative) to run the real baseline. The other
clauses are precedents and context for gap analysis and can be reviewed later.

| Clause id | Why the engine needs it |
|---|---|
| `uae.fl2-2019.art2` | Establishes the applicable health-data regime |
| `uae.pdpl.art2-2` | Shows why the PDPL is not assumed to govern health data |
| `uae.fl2-2019.art4` | Prohibition: no circulation of patient data outside permitted cases |
| `uae.fl2-2019.art16` | Safeguard: patient-information confidentiality and its exceptions |
| `uae.fl2-2019.art6` | Basis for the health-data oversight role's determinations |
| `dha.pp11.4-18-2` | Alert is investigated as a suspected incident, not a proven breach |
| `dha.pp11.4-18-4` | Breach-reporting period (unknown: candidate finding) |
| `dha.pp11.4-18-1` | A continuity plan must exist (h2); activation authority uncertain |
| `uae.ai-charter.human-oversight` | Human oversight principle with no owner (orphan-duty evidence) |
| `illus.telecom.incident-report` | Already illustrative: telecom reporting duty |
| `illus.telecom.regulator-information-request` | Already illustrative: regulator's telecom remit |

## Waiting on human

Answered on 2026-10-24: items 3-7 of the Phase 3 list, the spec 004 questions and the
CascadeGuard.md section 6 question (see Decisions). Re-approval needed
(gate 1): none (`policies/approvals.yaml`, `reapproval_needed: []`). Still open:

0. **Phase 4 MAJOR (test-breaker round 2), human gate:** no automated test drives the page in a
   browser; the flow is proven by the Playwright MCP run and its screenshots, as the human
   decided. A repeatable test would need the Python `playwright` package (listed in AGENTS.md as
   "Playwright (later)") as a dev dependency plus a browser download in CI. Add it now, or
   accept the MCP run for Phase 4?
   Also from round 2 (evidence-auditor, QUESTION-FOR-HUMAN): `uae.telecom-law.art14-5` keeps
   `kind: permission` although its mapping note says it is not a permission in this incident
   (7m); keep, or drop the `normalized` block as for the ITU and Charter clauses?
   From the phase-auditor (QUESTION-FOR-HUMAN): confirm in the PR that you approved the
   CascadeGuard.md section 6 wording (fbc51e1); approve or drop `.claude/launch.json` (a UI
   preview config, not under `.claude/agents/`).
1. **Clause review** of the remaining drafts, including 3p: `dha.pp11.4-18-5` takes its actor
   from 4.18.4, outside its quote (the two clauses stay separate).
2. **Sources missing from `policies/sources/`** (optional).
3. **3b:** the human checks the Arabic text of FL 2/2019 ("Health Authority").
   **3i:** the human looks for a complete DHA copy (footers 51/52 and 52/52 missing).

## Deferred MINOR findings (Phase 1 review)

- `normalized` blocks go beyond the quote in five clauses (see the triage). Settled by
  decision 5h (basis/mapping_note) and open questions h2 and 7p; they are now
  NEEDS-HUMAN-JUDGMENT, not FIX.
- ~~Book filenames as `source_file`; `normalized` names vs `roles.yaml`~~ Done in Phase 2
  (loader rejects book sources, duplicate YAML keys and stray `.yml` files;
  `check_clause_references` runs on every engine run, with tests).
- ~~`RepairProposal` list/dict fields~~ Done in Phase 3: edits and citations are tuples of
  frozen models with typed parameters.
- ~~Deep-freeze and AwareDatetime~~ Done in Phase 2: domain lists are tuples, and `at` and
  `start_time` are `AwareDatetime`. `ProposedAction.parameters` stays a dict; the engine copies
  each decision on receipt and logs only strings.
- Phase 2: `tests/unit/test_scenario.py` validates scenario clause references against all clauses,
  drafts included. Engine runs must use `load_engine_clauses()` or fixtures.

## Next step

1. Finish the Phase 4 review loop (round 3 for the reviewers that failed), push, open the PR.
2. Human: look at the screenshots in the PR, answer "Waiting on human" item 0, decide on merge.
