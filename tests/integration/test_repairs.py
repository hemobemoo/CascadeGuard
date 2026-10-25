"""Repair search and replay on the real clause set (Phase 3 "Done when")."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from cascadeguard.cli import format_search, load_world, main, run_scenario, search_repairs
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.engine.repair_search import SCRIPTED_LIMIT as SCRIPTED
from cascadeguard.engine.repair_search import ReplayComparison, SearchResult, search
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.orchestrator import run
from cascadeguard.simulation.replay import REPAIR_LABEL, replay
from cascadeguard.storage.audit import AuditStore
from cascadeguard.storage.export import comparison_markdown

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "scenarios" / "uae_health_access" / "expected_repairs.yaml"
BASELINE = ROOT / "scenarios" / "uae_health_access" / "expected_baseline.yaml"
SHARE = "share.network_incident_status.telecom_operator.health_service_operator"
OWNER = "owner.reverse_automated_lockouts.health_service_operator"
SUCCESS = f"{OWNER}+{SHARE}"
PATIENT_SHARE = "share.patient_account_records.health_service_operator.telecom_operator"


def expected() -> dict[str, Any]:
    return yaml.safe_load(EXPECTED.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def found() -> SearchResult:
    return search_repairs("uae_health_access")


def test_search_and_both_replays_reproduce_the_golden(found: SearchResult) -> None:
    golden = expected()
    assert found.summary() == golden["search"]
    assert found.comparison(SUCCESS).summary() == golden["successful"]
    assert found.comparison(SHARE).summary() == golden["unsuccessful"]


def test_successful_repair_resolves_every_failure(found: SearchResult) -> None:
    best = found.ranked[0]
    assert best.proposal.repair_id == SUCCESS  # resolved repairs rank first (ADR 0001)
    assert best.outcome == "resolved"
    assert not best.unmet_critical_goals and not best.remaining and not best.new_conflicts


def test_blockers_hidden_by_a_goal_met_another_way_are_masked_not_removed(
    found: SearchResult,
) -> None:
    """Human decision 4a: only a repair that removes a blocker's cause removes it."""
    c = found.comparison(SUCCESS)
    assert c.removed == (
        "information_deadlock:network_incident_status->health_service_operator",
        "orphan_duty:reverse_automated_lockouts",
    )
    assert c.masked == (
        "orphan_duty:activate_fallback_channel",
        "undefined_trigger:review_automated_lockouts",
    )
    assert c.critical_blockers_removed == 2
    assert "masked (goal met another way; cause still present)" in format_search(found)


def test_unsuccessful_repair_clears_the_deadlock_but_not_the_lockout(found: SearchResult) -> None:
    c = found.comparison(SHARE)
    assert c.removed == ("information_deadlock:network_incident_status->health_service_operator",)
    assert c.unmet_critical_goals == ("patient_access_restored",)
    assert "orphan_duty:reverse_automated_lockouts" in c.remaining


def test_hard_filter_discards_the_patient_record_share_under_art4_and_art16(
    found: SearchResult,
) -> None:
    dropped = {d.repair_id: d for d in found.discarded}
    assert set(dropped[PATIENT_SHARE].clause_ids) == {"uae.fl2-2019.art4", "uae.fl2-2019.art16"}
    assert all(PATIENT_SHARE not in c.proposal.repair_id for c in found.ranked)
    with pytest.raises(KeyError, match="discarded"):
        found.comparison(PATIENT_SHARE)


def test_no_replay_releases_patient_records_to_telecom(found: SearchResult) -> None:
    """Checked by data category, so a new patient fact would be caught too."""
    w = load_world("uae_health_access")
    category = {f.id: f.data_category for e in w.scenario.events for f in e.facts}
    for c in found.ranked:
        released = {
            category[e.detail]
            for e in c.replay.log
            if e.kind == "fact_released" and e.role == "telecom_operator"
        }
        assert "patient_account_records" not in released, c.proposal.repair_id


def test_ranking_is_lexicographic(found: SearchResult) -> None:
    keys = [
        (
            bool(c.new_conflicts),
            bool(c.unmet_critical_goals),
            len(c.unmet_critical_goals),
            -c.critical_blockers_removed,
            c.critical_blockers_masked,
            len(c.proposal.edits),
        )
        for c in found.ranked
    ]
    assert keys == sorted(keys)


def test_repairs_with_new_conflicts_rank_below_every_clean_repair(found: SearchResult) -> None:
    """Human decision 4e: ranked lower, never discarded."""
    flags = [bool(c.new_conflicts) for c in found.ranked]
    assert True in flags and flags == sorted(flags)
    assert not any(d.repair_id.startswith("requester.") for d in found.discarded)


def test_a_repair_that_adds_an_unfulfilled_duty_is_recorded_as_a_new_conflict(
    found: SearchResult,
) -> None:
    requester = [c for c in found.ranked if c.proposal.repair_id.startswith("requester.")]
    assert requester
    for c in requester:
        assert c.outcome == "introduces new conflict"
        assert c.new_conflicts == ("temporal_infeasibility:request_determination",)
        # Only the scripted-agent limit: the requester never attempts the new duty (4e).
        assert c.conflict_tags() == {"temporal_infeasibility:request_determination": SCRIPTED}
        assert not replace(c, replay=replace(c.replay, scripted=False)).conflict_tags()


@pytest.mark.parametrize("repair_id", [SHARE, SUCCESS])
def test_replay_is_the_identical_incident_except_for_the_repair(repair_id: str) -> None:
    """Same injects and decisions; fact releases differ (in both directions) only by the status
    now reaching the health operator; agent views differ only in that role's facts and its own
    accepted actions."""
    w = load_world("uae_health_access")
    seen: dict[str, list[RoleView]] = {"baseline": [], "replay": []}

    def recording(run_kind: str) -> dict[str, Any]:
        def wrap(agent: Any) -> Any:
            class Recorder:
                def observe(self, view: RoleView) -> Any:
                    seen[run_kind].append(view)
                    return agent.observe(view)

            return Recorder()

        return {rid: wrap(a) for rid, a in w.agents.items()}

    found = search_repairs("uae_health_access")
    p = found.comparison(repair_id).proposal
    base = run(w.scenario, w.roles, w.clauses, w.corpus_ids, recording("baseline"), w.label)
    rep = replay(w.scenario, w.roles, w.clauses, w.corpus_ids, recording("replay"), w.label, p)

    def entries(result: Any, kind: str) -> list[tuple[Any, ...]]:
        return [(e.minute, e.role, e.detail) for e in result.log if e.kind == kind]

    assert entries(base, "inject") == entries(rep, "inject")
    assert entries(base, "decision") == entries(rep, "decision")
    before, after = set(entries(base, "fact_released")), set(entries(rep, "fact_released"))
    assert before <= after
    assert {(role, fact) for _, role, fact in after - before} == {
        ("health_service_operator", "otp_delivery_status")
    }
    assert len(seen["baseline"]) == len(seen["replay"]) == 36
    flipped = {
        (a["role"], f"T+{a['minute']:02d} {a['action']}")
        for a in found.comparison(repair_id).changed_actions()
        if a["replay"] == "accepted"
    }
    for b, r in zip(seen["baseline"], seen["replay"], strict=True):
        assert (
            replace(b, facts=r.facts, own_history=r.own_history, role_clauses=r.role_clauses) == r
        )
        # The only clause difference: the repair's own rules, shown as not citable (Phase 5).
        assert set(b.role_clauses) <= set(r.role_clauses)
        added = set(r.role_clauses) - set(b.role_clauses)
        assert all(c.id.startswith("repair.") and not c.citable for c in added)
        extra_history = {(r.role_id, h) for h in set(r.own_history) - set(b.own_history)}
        assert set(b.own_history) <= set(r.own_history)
        assert extra_history <= flipped
        if b.role_id != "health_service_operator":
            assert b.facts == r.facts
        else:
            assert {f.id for f in r.facts} - {f.id for f in b.facts} <= {"otp_delivery_status"}
            assert {f.id for f in b.facts} <= {f.id for f in r.facts}


def test_search_does_not_change_the_baseline(found: SearchResult) -> None:
    golden = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert found.ranked[0].baseline.summary() == golden
    assert run_scenario("uae_health_access").summary() == golden


def test_repair_rules_are_labelled_hypothetical(found: SearchResult) -> None:
    labels = dict(found.comparison(SUCCESS).replay.loaded_clauses)
    repair_ids = [cid for cid in labels if cid.startswith("repair.")]
    assert len(repair_ids) == 2
    assert {labels[cid] for cid in repair_ids} == {REPAIR_LABEL}


def test_search_is_deterministic_across_processes() -> None:
    code = (
        "import json; from cascadeguard.cli import search_repairs; "
        "print(json.dumps(search_repairs('uae_health_access').summary(), sort_keys=True))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("0", "1", "4242")
    }
    assert len(outputs) == 1


def test_dynamic_hard_filter_discards_a_replay_that_lifts_a_restriction() -> None:
    """If a replay ever accepted an action the baseline held back under Art 4/16, the repair
    is discarded, even though no edit names that action."""
    w = load_world("uae_health_access")
    baseline = w.baseline()

    def leaky(p: Any) -> Any:
        result = replay(w.scenario, w.roles, w.clauses, w.corpus_ids, w.agents, w.label, p)
        log = tuple(
            e.model_copy(update={"kind": "accepted", "reasons": ()})
            if e.kind == "rejected" and e.data_category == "patient_account_records"
            else e
            for e in result.log
        )
        return replace(result, log=log)

    result = search(baseline, w.scenario, w.roles, RuleBook(w.clauses), leaky)
    assert not result.ranked
    lifted = [d for d in result.discarded if d.reason.startswith("the replay got around")]
    assert lifted
    assert all(set(d.clause_ids) == {"uae.fl2-2019.art4", "uae.fl2-2019.art16"} for d in lifted)


def test_markdown_labels_every_clause_and_states_the_qualification(found: SearchResult) -> None:
    text = comparison_markdown(found.comparison(SHARE))
    assert "`dha.pp11.4-18-1` [reviewed (interpreted)]" in text
    assert "not a confirmed legal or standards gap" in text
    assert "hypothetical rules, not source clauses" in text
    assert "Requires authorization: **yes**" in text


def test_cli_replay_exports_and_audits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "audit.duckdb"
    args = ["run", "uae_health_access", "--repair", SHARE, "--export", str(tmp_path)]
    assert main([*args, "--audit", str(db)]) == 0
    assert "Outcome: **partial**" in capsys.readouterr().out
    exported = {p.suffix for p in tmp_path.glob("uae_health_access-replay-*")}
    assert exported == {".json", ".md"}
    con = duckdb.connect(str(db))
    try:
        kinds = con.execute("SELECT kind, repair_id FROM runs ORDER BY run_id").fetchall()
        outcome = con.execute("SELECT outcome FROM comparisons").fetchall()
        events = con.execute("SELECT count(*) FROM events WHERE run_id = 2").fetchone()
    finally:
        con.close()
    assert kinds == [("baseline", None), ("replay", SHARE)]
    assert outcome == [("partial",)]
    assert events is not None and events[0] > 0


def test_audit_store_appends_runs(tmp_path: Path, found: SearchResult) -> None:
    store = AuditStore(tmp_path / "a.duckdb")
    try:
        c: ReplayComparison = found.comparison(SUCCESS)
        assert store.record_comparison(c) == (1, 2)
        assert store.record_comparison(c) == (3, 4)
    finally:
        store.close()


def test_cli_unknown_repair_fails_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", "uae_health_access", "--repair", "rewrite_the_law"]) == 2
    assert "unknown repair" in capsys.readouterr().out
