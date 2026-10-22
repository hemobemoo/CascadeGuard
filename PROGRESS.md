# PROGRESS — CascadeGuard

Session hand-off. Read this before doing anything (see `AGENTS.md`).

## Current phase

**Phase 1 — Domain, policy extraction, and scenario: built; review loop run, human gates open**
(branch `phase-1-domain-scenario`, PR open). The human must review the draft clauses (list in the
PR and below) and set `status: reviewed` on each one that checks out.

## Done

### Phase 0 — Tooling (merged, tag `phase-0`)
uv project on Python 3.12, Ruff, Pyright (strict), pytest, CLI stub, `.env.example`, `.gitignore`
(including the two books by filename), `README.md`.

### Phase 1 — Domain, policy extraction, and scenario
- **1a/1b Extraction + inventory:** `scripts/extract_pdf_text.py` → `policies/extracted/*.jsonl`
  and `_inventory.json`. Inventory table in `docs/policy-inventory.md`. Telecom Law pages 13–47
  have no extractable text (vector-outlined glyphs; OCR would be needed).
- **1c Domain:** `src/cascadeguard/domain/` (`base`, `policies`, `decisions`, `repairs`,
  `scenario`). Clause loader `src/cascadeguard/knowledge/loader.py`. Scenario loader
  `src/cascadeguard/simulation/loader.py`.
- **1d Scenario:** `scenarios/uae_health_access/` (`scenario.yaml`, `roles.yaml`, `README.md`).
- **1e Clauses:** 30 clauses in `policies/reviewed/*.yaml`: 28 `draft` (verbatim, verified against
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
- Telecom: the two telecom rules **stay illustrative** (human decision); no OCR.
- Breach-reporting period for health data: **stays unknown** (human decision); the PDPL Executive
  Regulations are not added. The unknown period is itself a candidate finding.
- `[...]` gaps: a test extracts the skipped text and fails on any qualifier, modal, number or
  cross-reference unless the gap is only a footnote marker or a margin requirement ID. FL 2/2019
  Art. 4 and PDPL Art. 2(2) are now quoted in full instead of with gaps.
- `PolicyClause.binding` and `page` are strict (no "yes"/1/"3" coercion), with tests
  (phase-auditor round 2).
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
| `dha.pp11.4-18-1` | Continuity plan: basis for a fallback channel |
| `uae.ai-charter.human-oversight` | Human oversight principle with no owner (orphan-duty evidence) |
| `illus.telecom.incident-report` | Already illustrative: telecom reporting duty |
| `illus.telecom.regulator-information-request` | Already illustrative: regulator's telecom remit |

## Waiting on human

1. ~~Commit the rule-file changes.~~ Done in 194103a ("Add reviewer subagents and human gates"),
   with the human's explicit approval. phase-auditor asks the human to confirm in PR #2 that the
   exact diffs to `AGENTS.md`, `START_PROMPT.md` and `.claude/agents/` in 194103a are approved.
2. ~~Reviewer subagents do not load.~~ They load now; the Phase 1 review loop ran (see
   `docs/review/phase-1-clause-triage.md`).
3. **Clause review** of the 28 drafts, in the order of `docs/review/phase-1-clause-triage.md`
   (minimal core set first). Reply with the clause IDs to set to `status: reviewed`.
4. ~~Issuer of "UAE Policy Foundation.pdf".~~ Decided; see Decisions.
5. ~~Book history purge.~~ Done; see "Approved gate-5 exceptions". Optional: ask GitHub Support to
   purge `refs/pull/1/head` (old commit `9f67523`) and cached views.
6. **Sources missing from `policies/sources/`** (optional): NIS2 Directive (EU) 2022/2555; Canada's
   Directive on Automated Decision-Making; Singapore's Model AI Governance Framework (incl. agentic
   AI); WHO guidance on AI for health; NCEMA 7000; Executive Regulation of FL 2/2019.
7. **Evidence questions (QUESTION-FOR-HUMAN / NEEDS-HUMAN-JUDGMENT)**, detail in the triage file:
   a. FL 2/2019: are lock records with mobile numbers "health data and information" (Art 4)?
   b. FL 2/2019: the translation defines "Health Authority" twice; could the portal operator be
      one? Check the Arabic (affects art6 mapping and Art 16 exception 5).
   c. PDPL Art 2(2)(e): is FL 2/2019 the health data's own legislation? Is the portal operator
      governmental (exclusion b)?
   d. Confirm or keep as "treated as applicable": FL 2/2019 and the DHA policy apply to the
      scenario (README "Applicable health-data regime", Decisions above).
   e. DHA policy: binding on DHA-licensed private entities? (`binding: unknown` on all DHA clauses.)
   f. DHA 4.18.4: the policy defines "UAE Data Protection Law" as Decree-Law 45/2021 (§4.2,
      pp.9-10) but says "the regulation that is more specialized/detailed in health will
      supersede". Does that precedence rule displace the PDPL-based reporting period for health
      data, or does the period still come from the PDPL Executive Regulations?
   g. DHA 4.18.5: who is the "UAE Information Office", and may the mapping keep only DHA?
   h. `normalized` action ids are links into the scenario's action catalogue (`roles.yaml`), not
      words from the text; notes now say so. evidence-auditor holds that any actor/action not in
      the quote stays FIX (5 clauses: `dha.pp11.4-18-1`, `uae.ai-charter.human-oversight`,
      `uae.ai-charter.safety`, `mocai.ethics.fallback-plan`, `itu.y3172.req-ml-mng-003`). The
      agent disagrees that renaming is required (the mapping is the purpose of `normalized`), so
      this is a human gate: accept the mapping approach, or require text-entailed actions (the
      engine would then need a separate clause-to-action mapping)?
   i. DHA PDF footers read "n/52" but the PDF has 50 pages (ends in references 5.23). Is the copy
      complete? No clause depends on the missing pages.
   j. `policies/extracted/_inventory.json` (committed) lists the two books' filenames, page counts
      and PDF Title/Author metadata (no text). Acceptable, or drop the books from the committed
      inventory?
   k. `cascadeguard_project_structure.txt` does not list `simulation/loader.py` (P1),
      `domain/base.py` or `docs/policy-inventory.md`. It is a human-owned file: add them, or keep
      the note in Decisions?

## Deferred MINOR findings (Phase 1 review)

- `normalized` blocks go beyond the quote in three non-core clauses: `itu.y3172.req-ml-mng-003`,
  `uae.ai-charter.safety`, `mocai.ethics.fallback-plan` (see triage). Settle with question 7h.
- `scenario.yaml:9` "nobody owns reversing the locks" is a hypothetical premise; never cite it as a
  corpus finding.
- Phase 2: `frozen=True` does not deep-freeze `list`/`dict` fields (`AgentDecision.proposed_actions`,
  `ProposedAction.parameters`, `InformationBoundary.visible_categories`). The read-only agent view
  must use tuples or frozen mappings; have test-breaker probe it.
- Phase 2: `AgentDecision.at` accepts a naive datetime; use `AwareDatetime`.
- Phase 2: `tests/unit/test_scenario.py` validates scenario clause references against all clauses,
  drafts included. Engine runs must use `load_engine_clauses()` or fixtures.

## Next step

1. Human: answer question 7 and give the clause IDs to mark reviewed (core set first). Do not merge
   PR #2 while clause review is open.
2. Phase 2 starts on `phase-2-engine` (branched from `phase-1-domain-scenario`) against synthetic
   fixture clauses under `tests/fixtures/`, addressing the two Phase 2 notes above.
