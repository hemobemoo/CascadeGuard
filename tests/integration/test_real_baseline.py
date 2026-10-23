"""The baseline failure reproduces exactly on the real clause set (core set reviewed 2026-10-23)."""

from pathlib import Path
from typing import Any

import yaml

from cascadeguard.cli import run_scenario
from cascadeguard.domain.policies import ClauseStatus
from cascadeguard.knowledge.loader import load_clauses

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "scenarios" / "uae_health_access" / "expected_baseline.yaml"


def expected() -> dict[str, Any]:
    return yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))


def test_real_corpus_baseline_reproduces_expected_exactly() -> None:
    assert run_scenario("uae_health_access").summary() == expected()


def test_real_corpus_baseline_uses_only_reviewed_and_illustrative_clauses() -> None:
    result = run_scenario("uae_health_access")
    assert result.clause_set.startswith("policies/reviewed")
    statuses = {c.id: c.status for c in load_clauses()}
    loaded = {cid for cid, _ in result.loaded_clauses}
    assert loaded
    assert {statuses[c] for c in loaded} <= {ClauseStatus.REVIEWED, ClauseStatus.ILLUSTRATIVE}


def test_real_corpus_diagnoses_the_designed_failures() -> None:
    failures = {f.id for f in run_scenario("uae_health_access").failures}
    assert failures == {
        "information_deadlock:network_incident_status->health_service_operator",
        "orphan_duty:reverse_automated_lockouts",
        "orphan_duty:activate_fallback_channel",
        "undefined_trigger:review_automated_lockouts",
    }
