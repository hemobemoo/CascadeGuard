# Corpus counts (generated)

Generated from `policies/` by `uv run python scripts/corpus_counts.py`; do not edit by hand
(`--check` and `tests/integration/test_corpus_counts.py` keep it, the README, the
submission-readiness status note and the report equal).

**Corpus:** 24 original PDFs (22 committed, 2 published books kept local), plus 3 local-only UAE Cyber Security Council PDFs (not redistributed), 7 web transcriptions and 1 OCR copy; 42 clauses in `policies/reviewed/` (19 reviewed, 2 illustrative, 21 draft; 21 loaded into the simulation) and 9 gap-example-only clauses (7 reviewed, 2 draft; never loaded).

| What | Count | Where |
|---|---|---|
| Original PDFs, committed | 22 | `policies/sources/` (hashes: policy inventory) |
| Published books (originals; context only, never committed) | 2 | gitignored |
| CSC PDFs, local only (not redistributed) | 3 | gitignored; `NOT_REDISTRIBUTED` |
| Web transcriptions | 7 | `policies/sources/web/` |
| OCR copies (derived) | 1 | `policies/sources/ocr/` |
| Clauses, reviewed | 19 | `policies/reviewed/` |
| Clauses, illustrative | 2 | `policies/reviewed/` |
| Clauses, draft (never loaded) | 21 | `policies/reviewed/` |
| Clauses loaded into the simulation (reviewed + illustrative) | 21 | engine, role views |
| Gap-example-only clauses, reviewed | 7 | `policies/gap_examples_only/` |
| Gap-example-only clauses, draft | 2 | `policies/gap_examples_only/` |
