# PROGRESS — CascadeGuard

Session hand-off. Read this before doing anything (see `AGENTS.md`).

## Current phase

**Phase 1 — Domain, policy extraction, and scenario: complete, awaiting human review**
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
- `page` is the 1-based PDF page index used in `policies/extracted/`, not the printed page number.
- Scenario loading lives in `simulation/loader.py` (not listed in the structure file; it is the
  natural home, and Phase 2 builds the rest of `simulation/` around it).
- Dev dependency `types-pyyaml` added: type stubs PyYAML needs under strict Pyright (not in the
  AGENTS.md list; flagged for approval).
- Draft clauses are not loaded by the engine. Until the human reviews them, the engine has only the
  2 illustrative clauses. Phase 2 cannot start meaningfully before the review.

## Open questions for the human

1. **Review the 28 draft clauses** (list in the Phase 1 PR) and set `status: reviewed`.
   Check `binding` too, especially for the DHA policy (`unknown`).
2. **Telecom Law pages 13–47 have no extractable text** (glyphs drawn as vector outlines; only
   OCR could recover them, which needs a new dependency). TDRA's duties and licensee
   obligations are probably on those pages. Two telecom rules are therefore `illustrative`. Options:
   a readable copy of the law, a TDRA regulation PDF, or keep them illustrative.
3. **Issuer of "UAE Policy Foundation.pdf".** It is a compilation that opens with the UAE Charter
   for the Development and Use of AI and prints no compiler or date. Who should be recorded as
   issuer, and should the Charter's date be recorded from another source?
4. **PDPL Executive Regulations** (not in the corpus) set the breach-reporting period that the DHA
   policy refers to. Add them, or keep the period unknown (which is itself a finding)?
5. **Sources missing from `policies/sources/`.** Rules depending on these stay `illustrative` until
   you add the PDFs: NIS2 Directive (EU) 2022/2555; Canada's Directive on Automated
   Decision-Making; Singapore's Model AI Governance Framework (incl. agentic AI); WHO guidance on
   AI for health; NCEMA 7000 business continuity; TDRA regulations beyond the Telecom Law;
   Executive Regulation of Federal Law No. 2 of 2019.
6. **Dev dependency `types-pyyaml`:** approve, or remove and relax Pyright for YAML calls?
7. **Book PDFs in git history:** the human chose to keep them (no history rewrite). Note: checking
   out or pulling across commit 914ee87 deletes the ignored book files from disk; restore with
   `git show 8b03fb5:"policies/sources/<file>" > "policies/sources/<file>"`.

## Next step

After approval and clause review: merge the Phase 1 PR, tag `main` as `phase-1`, push the tag.
Then Phase 2 on branch `phase-2-engine`: `simulation/state.py`, `boundaries.py`,
`orchestrator.py`; `engine/constraints.py`, `graph.py`, `diagnosis.py`; `agents/base.py`,
`scripted.py`; `scripted_decisions.yaml`; `expected_baseline.yaml`.
