from pathlib import Path

import pytest

from cascadeguard.cli import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "clauses"


def test_main_without_command_exits_cleanly() -> None:
    assert main([]) == 0


def test_run_prints_clause_set_timeline_and_diagnosis(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "uae_health_access", "--clauses", str(FIXTURES)]) == 0
    out = capsys.readouterr().out
    assert "Clause set: SYNTHETIC FIXTURES" in out
    assert "REJECTED telecom_operator: share_incident_status -> health_service_operator" in out
    assert "[information_deadlock] network_incident_status->health_service_operator" in out
    assert "illustrative (interpreted)" in out


def test_run_on_real_corpus_says_how_many_drafts_are_excluded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["run", "uae_health_access"]) == 0
    assert "draft clauses not loaded (awaiting human review)" in capsys.readouterr().out


def test_repair_is_not_available_before_phase_3() -> None:
    assert main(["run", "uae_health_access", "--repair", "r1"]) == 2
