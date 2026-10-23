"""Clause loader: duplicate keys, stray .yml files, book sources; normalized names vs roles.yaml."""

from pathlib import Path

import pytest

from cascadeguard.domain.policies import PolicyClause
from cascadeguard.knowledge.loader import ClauseLoadError, load_clauses
from cascadeguard.simulation.loader import (
    ScenarioLoadError,
    check_clause_references,
    load_scenario,
)

CLAUSE = """clauses:
  - id: dup.key
    title: t
    text: Some verbatim text.
    source_file: doc.pdf
    page: 1
    issuer: i
    jurisdiction: j
    document_date: unknown
    status: draft
    binding: false
"""


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    reviewed, sources = tmp_path / "reviewed", tmp_path / "sources"
    reviewed.mkdir()
    sources.mkdir()
    (sources / "doc.pdf").write_bytes(b"%PDF-")
    return reviewed, sources


def test_duplicate_keys_are_rejected_not_silently_overwritten(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    (reviewed / "c.yaml").write_text(CLAUSE + "    status: reviewed\n", "utf-8")
    with pytest.raises(ClauseLoadError, match="duplicate keys"):
        load_clauses(reviewed, sources)


def test_a_stray_yml_file_fails_the_load(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    (reviewed / "c.yaml").write_text(CLAUSE, "utf-8")
    (reviewed / "b.yml").write_text("clauses: [{id: bad}]\n", "utf-8")
    with pytest.raises(ClauseLoadError, match=r"\.yaml"):
        load_clauses(reviewed, sources)


def test_a_published_book_is_never_a_clause_source(dirs: tuple[Path, Path]) -> None:
    reviewed, sources = dirs
    book = "The Oxford Handbook of AI Governance.pdf"
    (sources / book).write_bytes(b"%PDF-")
    (reviewed / "c.yaml").write_text(CLAUSE.replace("doc.pdf", book), "utf-8")
    with pytest.raises(ClauseLoadError, match="book"):
        load_clauses(reviewed, sources)


def test_repository_clauses_name_only_known_roles_and_actions() -> None:
    _, roles = load_scenario("uae_health_access", {c.id for c in load_clauses()})
    check_clause_references(load_clauses(), roles)


@pytest.mark.parametrize(
    ("field", "value"),
    [("actor", "helth_service_operator"), ("action", "reverse_automated_lockout")],
)
def test_a_typo_in_normalized_is_rejected(field: str, value: str) -> None:
    _, roles = load_scenario("uae_health_access", {c.id for c in load_clauses()})
    normalized = {
        "basis": "stated",
        "kind": "permission",
        "actor": "health_service_operator",
        "action": "reverse_automated_lockouts",
        field: value,
    }
    clause = PolicyClause.model_validate(
        {
            "id": "typo",
            "title": "t",
            "text": "x",
            "issuer": "i",
            "jurisdiction": "j",
            "document_date": "unknown",
            "status": "illustrative",
            "binding": False,
            "notes": "n",
            "normalized": normalized,
        }
    )
    with pytest.raises(ScenarioLoadError, match=value):
        check_clause_references([clause], roles)
