"""The baseline failure reproduces exactly, with ScriptedAgents and synthetic fixture clauses."""

from pathlib import Path
from typing import Any

import yaml

from cascadeguard.cli import run_scenario
from cascadeguard.knowledge.loader import REVIEWED_DIR

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CLAUSES = ROOT / "tests" / "fixtures" / "clauses"
EXPECTED = ROOT / "tests" / "fixtures" / "uae_health_access" / "expected_baseline.yaml"


def expected() -> dict[str, Any]:
    return yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))


def test_baseline_reproduces_expected_exactly() -> None:
    result = run_scenario("uae_health_access", FIXTURE_CLAUSES)
    assert result.summary() == expected()


def test_baseline_is_deterministic() -> None:
    first = run_scenario("uae_health_access", FIXTURE_CLAUSES)
    second = run_scenario("uae_health_access", FIXTURE_CLAUSES)
    assert first.log == second.log
    assert first.failures == second.failures
    assert first.graph.edges() == second.graph.edges()


def test_baseline_diagnoses_the_designed_failures() -> None:
    failures = {f.id: f for f in run_scenario("uae_health_access", FIXTURE_CLAUSES).failures}
    assert set(failures) == {
        "information_deadlock:network_incident_status->health_service_operator",
        "orphan_duty:reverse_automated_lockouts",
        "orphan_duty:activate_fallback_channel",
        "undefined_trigger:review_automated_lockouts",
    }
    for failure in failures.values():
        assert "not a confirmed legal or standards gap" in failure.qualification
        assert "SYNTHETIC FIXTURES" in failure.qualification


def test_safeguard_holds_patient_records_never_reach_telecom() -> None:
    result = run_scenario("uae_health_access", FIXTURE_CLAUSES)
    released = [e for e in result.log if e.kind == "fact_released" and e.role == "telecom_operator"]
    assert "locked_account_records" not in {e.detail for e in released}


def test_real_corpus_run_labels_its_clause_set_and_rejects_draft_citations(
    tmp_path: Path,
) -> None:
    """Since gate 1 on 2026-10-28 the scripted agents cite no draft on the real corpus, so the
    rejection is checked on a copy where the one clause they cited before (eu.gdpr.art33-1) is a
    draft again."""
    result = run_scenario("uae_health_access")
    assert result.clause_set.startswith("policies/reviewed")
    assert not [f for f in result.findings if f.kind == "draft_citation"]

    copy = tmp_path / "reviewed"
    copy.mkdir()
    for path in REVIEWED_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["clauses"] = [
            {**c, "status": "draft"} if c["id"] == "eu.gdpr.art33-1" else c for c in data["clauses"]
        ]
        (copy / path.name).write_text(yaml.safe_dump(data), encoding="utf-8")
    result = run_scenario("uae_health_access", copy)
    loaded = {cid for cid, _ in result.loaded_clauses}
    drafts = {c for f in result.findings if f.kind == "draft_citation" for c in f.clause_ids}
    assert drafts == {"eu.gdpr.art33-1"} and not drafts & loaded
    rejected = result.summary()["rejected_decisions"]
    assert [(d["role"], d["reasons"]) for d in rejected] == [
        ("policy_legal_adviser", ["draft_citation"])
    ]
