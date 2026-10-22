# PROGRESS — CascadeGuard

Session hand-off. Read this before doing anything (see `AGENTS.md`).

## Current phase

**Phase 1 — Domain, policy extraction, and scenario: built; review loop and human gates open**
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
- **Health-data regime:** Federal Law No. 2 of 2019 applies (Art. 2). The PDPL is not assumed to
  apply, because Art. 2(2)(e) excludes health data that has its own legislation. The scenario places
  the portal in Dubai, so the DHA Health Data Protection and Confidentiality Policy also applies.
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
- Draft clauses are not loaded by the engine. Phase 2 may be built against synthetic fixture
  clauses under `tests/fixtures/` (AGENTS.md "Human gates"); fixtures never prove the real scenario.
- **Dubai Law No. 26 of 2015 is not drafted as a clause.** Art. 3 applies it to government
  entities and to "Persons ... who are determined by the Competent Entity"; nothing in the corpus
  shows the scenario's private operators are determined. It governs dissemination and exchange of
  "Dubai Data" through the Competent Entity's platform, not an incident channel between operators,
  and Art. 13(a) is without prejudice to data legislation in force, so it cannot override
  FL 2/2019 Art. 16. Whether it could support a telecom-to-health status share is a question for
  the human (candidate only).

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

1. **Commit the rule-file changes.** My commit of `AGENTS.md`, `START_PROMPT.md`,
   `cascadeguard_project_structure.txt` and `.claude/agents/` as "Add reviewer subagents and human
   gates" was blocked by the session's permission check. The files are uncommitted in the working
   tree. Commit them yourself, or allow the commit.
2. **Reviewer subagents do not load in the current session** (`evidence-auditor`, `phase-auditor`
   not found; agent definitions are read when a session starts). The review loop for Phase 1 has
   not run. Start a new session after committing them, then run step 1.
3. **Clause review** of the 28 drafts (start with the minimal core set above). The evidence triage
   that orders the review list is not produced yet (needs `evidence-auditor`).
4. **Issuer of "UAE Policy Foundation.pdf".** The human's decision did not reach this session;
   still recorded as "UAE Government (compiled document; compiler not stated in the PDF)".
5. **Book history purge.** Listed by the human as an open gate (force-push and history rewrite,
   AGENTS.md gate 5). Earlier the human said to keep the books in history; the exact instruction
   needs confirming before anything is rewritten. Note: checking out or pulling across commit
   914ee87 deletes the ignored book files from disk; restore with
   `git show 8b03fb5:"policies/sources/<file>" > "policies/sources/<file>"`.
6. **Sources missing from `policies/sources/`** (optional): NIS2 Directive (EU) 2022/2555; Canada's
   Directive on Automated Decision-Making; Singapore's Model AI Governance Framework (incl. agentic
   AI); WHO guidance on AI for health; NCEMA 7000; Executive Regulation of FL 2/2019.

## Next step

1. Human commits the rule files (gate 1 above) and starts a new session so the reviewer subagents
   load.
2. Run `evidence-auditor` and `phase-auditor` on `phase-1-domain-scenario` (PR #2); fix BLOCKER
   and MAJOR findings, at most three rounds; save the triage to
   `docs/review/phase-1-clause-triage.md`; update the PR body with both verdicts and the review
   list ordered NEEDS-HUMAN-JUDGMENT, then FIX-resolved, then CLEAN, showing each `[...]` gap's
   skipped text.
3. Do not merge PR #2 (clause review and book-history gates are open). Phase 2 may start on
   `phase-2-engine` against synthetic fixture clauses under `tests/fixtures/`.
