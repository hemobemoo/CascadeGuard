"""Fixture clauses must behave in the engine exactly as the real clauses with the same id would."""

from pathlib import Path

from cascadeguard.domain.policies import ClauseStatus
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.knowledge.loader import load_clauses

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "clauses"


def test_every_fixture_id_exists_in_the_corpus_and_is_labelled_synthetic() -> None:
    real = {c.id for c in load_clauses()}
    for fixture in load_clauses(FIXTURES):
        assert fixture.id in real
        assert fixture.status is ClauseStatus.ILLUSTRATIVE
        assert fixture.title.startswith("SYNTHETIC FIXTURE")


def test_fixtures_mirror_the_real_normalized_reading_and_authority() -> None:
    real = {c.id: c for c in load_clauses()}
    fixtures = {c.id: c for c in load_clauses(FIXTURES)}
    real_rules = RuleBook({i: real[i] for i in fixtures})
    fixture_rules = RuleBook(fixtures)
    for cid, fixture in fixtures.items():
        source = real[cid]
        guidance = source.binding is False and source.status is not ClauseStatus.ILLUSTRATIVE
        assert fixture.normalized == (None if guidance else source.normalized), cid
        assert (fixture.binding == "unknown") == (source.binding == "unknown"), cid
        n = source.normalized
        if n is not None and n.actor != "any":
            assert fixture_rules.authority(n.actor, n.action) == real_rules.authority(
                n.actor, n.action
            ), cid
            assert fixture_rules.obligations_for(n.action) == real_rules.obligations_for(n.action)
