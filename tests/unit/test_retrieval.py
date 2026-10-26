"""knowledge/retrieval.py: role clauses follow the engine's scope rule; extracted search never
touches the books and is deterministic."""

import json
from pathlib import Path

from cascadeguard.cli import load_world, search_repairs
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.knowledge.retrieval import (
    CONTEXT_LABEL,
    NOT_CITABLE_LABEL,
    clauses_for_role,
    search_extracted,
)
from cascadeguard.simulation.replay import apply_repair

SUCCESS = (
    "owner.reverse_automated_lockouts.health_service_operator.30m"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)


def test_role_clauses_are_exactly_what_the_role_may_cite() -> None:
    w = load_world("uae_health_access")
    book = RuleBook(w.clauses)
    for role in w.roles.roles:
        got = clauses_for_role(w.clauses, w.corpus_ids, role.id, role.allowed_actions)
        expected = sorted(
            cid for cid in w.clauses if book.concerns(cid, role.id, role.allowed_actions)
        )
        assert [c.id for c in got] == expected
        labels = dict((c.id, c.status_label) for c in w.clauses.values())
        assert all(c.status_label == labels[c.id] and c.citable for c in got)
    # Not every role sees every clause (the policy adviser does: provide_policy_analysis).
    sizes = {
        r.id: len(clauses_for_role(w.clauses, w.corpus_ids, r.id, r.allowed_actions))
        for r in w.roles.roles
    }
    assert min(sizes.values()) < len(w.clauses)


def test_repair_rules_are_shown_but_not_citable() -> None:
    w = load_world("uae_health_access")
    proposal = search_repairs("uae_health_access").comparison(SUCCESS).proposal
    _, roles, clauses = apply_repair(w.scenario, w.roles, w.clauses, proposal)
    health = roles.role("health_service_operator")
    got = clauses_for_role(clauses, w.corpus_ids, health.id, health.allowed_actions)
    repair = [c for c in got if c.id.startswith("repair.")]
    assert repair
    assert all(not c.citable and c.status_label == NOT_CITABLE_LABEL for c in repair)


def test_search_skips_books_and_is_deterministic(tmp_path: Path) -> None:
    rows = {
        "Some Policy.jsonl": [
            {"source_file": "Some Policy.pdf", "page": 2, "text": "incident report duty"}
        ],
        "Abhivardhan book.jsonl": [
            {"source_file": "Abhivardhan book.pdf", "page": 1, "text": "incident incident incident"}
        ],
        "Other.jsonl": [
            {"source_file": "The Oxford Handbook x.pdf", "page": 3, "text": "incident report"},
            {"source_file": "Other.pdf", "page": 1, "text": "incident"},
        ],
    }
    for name, pages in rows.items():
        (tmp_path / name).write_text("\n".join(json.dumps(p) for p in pages), encoding="utf-8")
    first = search_extracted("incident report", extracted_dir=tmp_path)
    assert first == search_extracted("incident report", extracted_dir=tmp_path)
    assert [(s.source_file, s.page) for s in first] == [("Some Policy.pdf", 2), ("Other.pdf", 1)]
    assert all(s.label == CONTEXT_LABEL for s in first)
    assert search_extracted("", extracted_dir=tmp_path) == ()


def test_search_on_the_real_extracted_text_never_returns_a_book() -> None:
    for s in search_extracted("artificial intelligence ethics governance", limit=50):
        assert "abhivardhan" not in s.source_file.casefold()
        assert "oxford handbook" not in s.source_file.casefold()
