"""The one authoritative count of the policy sources and clauses (Task 5, human brief 2026-11-05).

Computed from policies/ only, the same way in a full checkout, a clone and CI: the two published
books and the not-redistributed CSC PDFs are never committed, so they are counted from the
loader's lists (BOOK_MARKERS is fixed at two books; NOT_REDISTRIBUTED pins three files), not from
the disk. Writes docs/corpus-counts.md; README, the submission-readiness status note and the
report repeat its sentence (tests/integration/test_corpus_counts.py keeps them equal).

    uv run python scripts/corpus_counts.py [--check]
"""

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from cascadeguard.domain.policies import ClauseStatus
from cascadeguard.knowledge.loader import (
    BOOK_MARKERS,
    NOT_REDISTRIBUTED,
    PROJECT_ROOT,
    SOURCES_DIR,
    gap_example_folder_clauses,
    load_clauses,
)

OUTPUT = PROJECT_ROOT / "docs" / "corpus-counts.md"


@dataclass(frozen=True)
class Counts:
    committed: int  # original PDFs committed in policies/sources/
    books: int  # the published books: originals, context only, never committed
    local_only: int  # not redistributed (NOT_REDISTRIBUTED)
    web: int
    ocr: int
    clauses: Counter[str]  # policies/reviewed/ by status
    gap: Counter[str]  # policies/gap_examples_only/ by status

    @property
    def originals(self) -> int:
        return self.committed + self.books

    @property
    def loaded(self) -> int:
        return self.clauses["reviewed"] + self.clauses["illustrative"]


def counts(sources: Path = SOURCES_DIR) -> Counts:
    def committed_pdf(p: Path) -> bool:
        name = p.name
        return not any(m in name.casefold() for m in BOOK_MARKERS) and name not in NOT_REDISTRIBUTED

    return Counts(
        committed=sum(1 for p in sources.glob("*.pdf") if committed_pdf(p)),
        books=len(BOOK_MARKERS),
        local_only=len(NOT_REDISTRIBUTED),
        web=len(list((sources / "web").glob("*.pdf"))),
        ocr=len(list((sources / "ocr").glob("*.pdf"))),
        clauses=Counter(str(c.status) for c in load_clauses()),
        gap=Counter(str(c.status) for c in gap_example_folder_clauses()),
    )


def sentence(c: Counts) -> str:
    """The sentence the README, the readiness status note and the report repeat."""
    reviewed, illustrative, draft = (c.clauses[s.value] for s in _ORDER)
    return (
        f"{c.originals} original PDFs ({c.committed} committed, {c.books} published books kept "
        f"local), plus {c.local_only} local-only UAE Cyber Security Council PDFs (not "
        f"redistributed), {c.web} web transcriptions and {c.ocr} OCR copy; "
        f"{sum(c.clauses.values())} clauses in `policies/reviewed/` ({reviewed} reviewed, "
        f"{illustrative} illustrative, {draft} draft; {c.loaded} loaded into the simulation) and "
        f"{sum(c.gap.values())} gap-example-only clauses ({c.gap['reviewed']} reviewed, "
        f"{c.gap['draft']} draft; never loaded)."
    )


_ORDER = (ClauseStatus.REVIEWED, ClauseStatus.ILLUSTRATIVE, ClauseStatus.DRAFT)


def render(c: Counts) -> str:
    return f"""# Corpus counts (generated)

Generated from `policies/` by `uv run python scripts/corpus_counts.py`; do not edit by hand
(`--check` and `tests/integration/test_corpus_counts.py` keep it, the README, the
submission-readiness status note and the report equal).

**Corpus:** {sentence(c)}

| What | Count | Where |
|---|---|---|
| Original PDFs, committed | {c.committed} | `policies/sources/` (hashes: policy inventory) |
| Published books (originals; context only, never committed) | {c.books} | gitignored |
| CSC PDFs, local only (not redistributed) | {c.local_only} | gitignored; `NOT_REDISTRIBUTED` |
| Web transcriptions | {c.web} | `policies/sources/web/` |
| OCR copies (derived) | {c.ocr} | `policies/sources/ocr/` |
| Clauses, reviewed | {c.clauses["reviewed"]} | `policies/reviewed/` |
| Clauses, illustrative | {c.clauses["illustrative"]} | `policies/reviewed/` |
| Clauses, draft (never loaded) | {c.clauses["draft"]} | `policies/reviewed/` |
| Clauses loaded into the simulation (reviewed + illustrative) | {c.loaded} | engine, role views |
| Gap-example-only clauses, reviewed | {c.gap["reviewed"]} | `policies/gap_examples_only/` |
| Gap-example-only clauses, draft | {c.gap["draft"]} | `policies/gap_examples_only/` |
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Count the policy sources and clauses.")
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs")
    args = parser.parse_args()
    text = render(counts())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{OUTPUT.relative_to(PROJECT_ROOT)} is stale: run scripts/corpus_counts.py")
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
