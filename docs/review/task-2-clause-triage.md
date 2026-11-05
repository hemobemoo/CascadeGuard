# Task 2 clause triage (NIST SP 800-34 Rev. 1)

Evidence-auditor, branch `gap-fallback-example`. Round 1 (1554bce): FAIL, one FIX (fixed in
f8f38c9). Round 2 (f8f38c9): **PASS**. Option (c), round 3 (3ffe37b): **PASS** (both CLEAN).
Gate 1 (human, 2026-11-06), scoped: both reviewed **as gap examples only**, in
`policies/gap_examples_only/`, never loaded into the simulation; quotes checked by the human
against PDF pp. 15 and 50.

| clause_id | source_file | viewer page | round 1 | round 2 |
|---|---|---|---|---|
| nist.sp800-34.alternate-manual-means | nistspecialpublication800-34r1.pdf | 15 (printed 1) | CLEAN | CLEAN |
| nist.sp800-34.activation-by-designated-authority | nistspecialpublication800-34r1.pdf | 50 (printed 36) | FIX: footnote 31 only summarised; title dropped "should" | CLEAN |

Round 1 FIX, applied: footnote 31 word for word in the notes; the ISCP Coordinator sentence of
4.2.1 noted; "should" kept in the title; printed pages recorded. Round 2 MINOR, applied: "with a
successor identified if necessary". The other 23 draft and 2 illustrative clauses are unchanged
from main and re-checked verbatim.

Answered 2026-11-06 (gate 7): the human approved both entries for
orphan_duty:activate_fallback_channel with their own relevance lines. Round 3 MINOR, for the
human: the alternate-means relevance line says "a recommendation" and "typically for short-term
disruptions", while the source text is descriptive and says "typically acceptable for only
short-term disruptions" (the quote under it keeps that). The earlier question was: is US information-system contingency
guidance (not AI-specific; "should"; manual means "typically acceptable for only short-term
disruptions") a fair example for orphan_duty:activate_fallback_channel? Any gap_examples entry
keeps that condition and the "candidate finding" wording.
