"""Clause sources stay inside policies/sources, books are refused in any case, no stray files."""

from pathlib import Path

import pytest

from cascadeguard.domain.policies import ClauseStatus
from cascadeguard.knowledge.loader import ClauseLoadError, load_clauses

CLAUSE = """clauses:
  - id: x.clause
    title: t
    text: Some verbatim text.
    source_file: {source}
    page: 1
    issuer: i
    jurisdiction: j
    document_date: unknown
    status: reviewed
    binding: false
"""


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    reviewed, sources = tmp_path / "reviewed", tmp_path / "sources"
    reviewed.mkdir()
    sources.mkdir()
    (sources / "doc.pdf").write_bytes(b"%PDF-")
    return reviewed, sources


def write(reviewed: Path, source: str, extra: str = "") -> None:
    (reviewed / "c.yaml").write_text(CLAUSE.format(source=f'"{source}"') + extra, "utf-8")


@pytest.mark.parametrize(
    "source",
    [
        "artificial intelligence ethics and international law - 2nd -- abhivardhan --.pdf",
        "THE OXFORD HANDBOOK OF AI GOVERNANCE.pdf",
    ],
)
def test_books_are_refused_whatever_the_case(dirs: tuple[Path, Path], source: str) -> None:
    reviewed, sources = dirs
    (sources / source).write_bytes(b"%PDF-")
    write(reviewed, source)
    with pytest.raises(ClauseLoadError, match="book"):
        load_clauses(reviewed, sources)


@pytest.mark.parametrize("source", ["../doc.pdf", "web/../doc.pdf", "sub\\\\doc.pdf"])
def test_source_paths_must_stay_plain_and_inside_sources(
    dirs: tuple[Path, Path], source: str
) -> None:
    reviewed, sources = dirs
    write(reviewed, source)
    with pytest.raises(ClauseLoadError, match="source_file"):
        load_clauses(reviewed, sources)


def test_absolute_source_path_is_refused(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    write(reviewed, (sources / "doc.pdf").resolve().as_posix())
    with pytest.raises(ClauseLoadError, match="source_file"):
        load_clauses(reviewed, sources)


@pytest.mark.parametrize("stray", ["notes.txt", "c.yaml.bak", "C2.YAML", "sub"])
def test_stray_files_and_subdirectories_fail_the_load(dirs: tuple[Path, Path], stray: str) -> None:
    reviewed, sources = dirs
    write(reviewed, "doc.pdf")
    if stray == "sub":
        (reviewed / "sub").mkdir()
    else:
        (reviewed / stray).write_text("clauses: []\n", "utf-8")
    with pytest.raises(ClauseLoadError, match="allowed"):
        load_clauses(reviewed, sources)


def test_readme_is_allowed_next_to_clause_files(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    write(reviewed, "doc.pdf")
    (reviewed / "README.md").write_text("# fields\n", "utf-8")
    assert [c.id for c in load_clauses(reviewed, sources)] == ["x.clause"]


def test_extra_top_level_keys_are_refused(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    write(reviewed, "doc.pdf", extra="status_override: reviewed\n")
    with pytest.raises(ClauseLoadError, match="only a 'clauses' list"):
        load_clauses(reviewed, sources)


def test_blank_text_is_refused(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    (reviewed / "c.yaml").write_text(
        CLAUSE.format(source='"doc.pdf"').replace("Some verbatim text.", "' '"), "utf-8"
    )
    with pytest.raises(ClauseLoadError):
        load_clauses(reviewed, sources)


def test_repository_illustrative_clauses_are_binding_false() -> None:
    """Only test fixtures may keep binding: unknown on an illustrative clause."""
    for clause in load_clauses():
        if clause.status is ClauseStatus.ILLUSTRATIVE:
            assert clause.binding is False, clause.id


@pytest.mark.parametrize("source", ["web./doc.pdf", "web /doc.pdf", "ocr./doc.pdf", " doc.pdf"])
def test_names_windows_would_trim_are_refused(dirs: tuple[Path, Path], source: str) -> None:
    """Windows drops a trailing dot or space, so these would open web/ or ocr/ files while
    escaping the web and OCR rules, which read the spelling."""
    reviewed, sources = dirs
    for folder in ("web", "ocr"):
        (sources / folder).mkdir(exist_ok=True)
        (sources / folder / "doc.pdf").write_bytes(b"%PDF-")
    write(reviewed, source)
    with pytest.raises(ClauseLoadError, match="source_file"):
        load_clauses(reviewed, sources)
