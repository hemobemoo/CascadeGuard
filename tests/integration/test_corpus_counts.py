"""Task 5: one authoritative count of sources and clauses, generated from policies/
(scripts/corpus_counts.py), repeated word for word in the README and the readiness status note,
and in the report's short form."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def corpus_counts() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "corpus_counts", ROOT / "scripts" / "corpus_counts.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["corpus_counts"] = module
    spec.loader.exec_module(module)
    return module


def read(rel: str) -> str:
    return " ".join((ROOT / rel).read_text(encoding="utf-8").replace(">", " ").split())


def test_the_generated_counts_file_is_current() -> None:
    cc = corpus_counts()
    assert (ROOT / "docs" / "corpus-counts.md").read_text(encoding="utf-8").replace(
        "\r\n", "\n"
    ) == cc.render(cc.counts())


def test_readme_and_the_readiness_note_repeat_the_sentence() -> None:
    cc = corpus_counts()
    sentence = cc.sentence(cc.counts())
    assert sentence in read("README.md")
    assert sentence in read("docs/submission-readiness.md")


def test_the_report_states_the_same_counts() -> None:
    cc = corpus_counts()
    c = cc.counts()
    r = c.clauses
    short = (
        f"{c.loaded} clauses are loaded ({r['reviewed']} reviewed, {r['illustrative']} "
        f"illustrative) of {sum(r.values())} in policies/reviewed/, drafts never; the corpus is "
        f"{c.originals} original PDFs ({c.books} published books, context only, never a clause "
        f"source), {c.local_only} local-only CSC PDFs (gap examples only) and {c.web} web "
        "transcriptions."
    )
    assert short in read("docs/report/cascadeguard-report.md")


def test_the_counts_do_not_depend_on_local_only_files(tmp_path: Path) -> None:
    """A clone or CI has neither the books nor the CSC PDFs; the counts must be the same."""
    cc = corpus_counts()
    sources = ROOT / "policies" / "sources"
    copy = tmp_path / "sources"
    for sub in ("", "web", "ocr"):
        (copy / sub).mkdir(parents=True, exist_ok=True)
        for p in (sources / sub).glob("*.pdf"):
            local_only = p.name in cc.NOT_REDISTRIBUTED or any(
                m in p.name.casefold() for m in cc.BOOK_MARKERS
            )
            if not local_only:
                (copy / sub / p.name).write_bytes(b"%PDF-")
    assert cc.counts(copy) == cc.counts()
    assert cc.counts().committed == 22 and cc.counts().originals == 24  # AGENTS.md: 24 originals


def test_the_inventory_opening_agrees() -> None:
    c = corpus_counts().counts()
    assert (
        f"The {c.originals} original PDFs in `policies/sources/` ({c.committed} committed; the "
        f"{c.books} published books kept local;"
    ) in read("docs/policy-inventory.md")
