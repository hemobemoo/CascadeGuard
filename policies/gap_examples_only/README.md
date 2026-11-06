# Gap examples only

Clauses reviewed by the human **as gap-analysis examples only** (human decision 2026-11-06).
They are never loaded into the simulation (engine, role views, knowledge base, adviser). Only
the report builder reads them, for `scenarios/<id>/gap_examples.yaml` and
`docs/gap-analysis.md`, where each is shown with its status label plus "reviewed as a gap
example; not loaded into the simulation". Same fields and review rules as
`policies/reviewed/` (verbatim quote, page, gate 1, digests in `policies/approvals.yaml`). An
edit to one of them sets it back to `status: draft` and lists it under `reapproval_needed`, in
this folder; while it is a draft the report builder does not show it and refuses a
gap_examples.yaml entry that maps it.

`uae_csc_cyber.yaml` (Task 3, 2026-11-06) holds clauses from three UAE Cyber Security Council
PDFs that are not redistributed (reproduction needs the CSC's consent): the PDFs and their
extracted text are local only. Each clause's notes give the viewer and printed page and the
version as printed; `tests/integration/test_uae_cyber_sources.py` checks the quotes where the
text is present and the committed page digests everywhere.
