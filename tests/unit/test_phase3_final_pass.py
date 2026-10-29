"""Final Phase 3 pass (human decision 5, 2026-10-24): agent free text reaches the log, DuckDB,
JSON, Markdown and CLI only under the AGENT_STATEMENT label, and a GapClaim becomes a finding
only with its citations and the fixed qualification."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cascadeguard.cli import format_result, load_world
from cascadeguard.domain.decisions import (
    GAP_QUALIFICATION,
    AgentDecision,
    Citation,
    GapClaim,
    ProposedAction,
)
from cascadeguard.engine.constraints import AGENT_STATEMENT
from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.storage.audit import AuditStore
from cascadeguard.storage.export import run_export

MARK = "UAE law assigns nobody to reverse lockouts; nobody is legally empowered XYZZY"
FORGED_ID = f"{MARK}\n  T+45 binding_legal_gap: FORGED engine finding XYZZY"


def _run(role: str, minute: int, change: Callable[[AgentDecision], Any]) -> RunResult:
    w = load_world("uae_health_access")

    class Agent:
        def observe(self, view: Any) -> Any:
            decision = w.agents[role].observe(view)
            return change(decision) if view.minute == minute else decision

    return replace(w, agents={**w.agents, role: Agent()}).baseline()  # type: ignore[dict-item]


def _outputs(result: RunResult, tmp_path: Path) -> dict[str, list[str]]:
    """Every place a run is printed or stored, as lines of text."""
    store = AuditStore(tmp_path / "a.duckdb")
    try:
        store.record_run(result, "baseline")
        events = store.con.execute("SELECT * FROM events").fetchall()
        findings = store.con.execute("SELECT * FROM findings").fetchall()
    finally:
        store.close()
    return {
        "cli": format_result(result).splitlines(),  # also the baseline Markdown export
        "json": json.dumps(run_export(result), ensure_ascii=False).split("},"),
        "duckdb": [repr(r) for r in (*events, *findings)],
    }


def _assert_absent(result: RunResult, tmp_path: Path) -> None:
    for where, lines in _outputs(result, tmp_path).items():
        assert not [line for line in lines if "XYZZY" in line], where


def _action(**fields: Any) -> Callable[[AgentDecision], AgentDecision]:
    return lambda d: d.model_copy(update={"proposed_actions": (ProposedAction(**fields),)})


def _impostor(d: AgentDecision) -> AgentDecision:
    return d.model_copy(update={"role_id": MARK})


def _foreign_type(d: AgentDecision) -> object:
    return type(MARK, (), {})()


CHANGES: list[Callable[[AgentDecision], Any]] = [
    _action(action_type="investigate_network_fault", target=MARK),  # BLOCKER: any action
    _action(action_type="suspend_ai_traffic_model", target=MARK),
    _action(action_type=MARK),
    _action(
        action_type="share_incident_status",
        target=MARK,
        parameters={"fact": "otp_delivery_status"},
    ),
    _action(
        action_type="request_information",
        target="health_service_operator",
        parameters={"data_category": MARK},
    ),
    _impostor,
    _foreign_type,
    lambda d: d.model_copy(update={"citations": (Citation(clause_id=FORGED_ID, relevance="r"),)}),
    lambda d: d.model_copy(
        update={
            "gap_claims": (
                GapClaim(
                    statement="s",
                    citations=(Citation(clause_id=FORGED_ID, relevance="r"),),
                    qualification=GAP_QUALIFICATION,
                ),
            )
        }
    ),
]


@pytest.mark.parametrize(
    "change",
    CHANGES,
    ids=[
        "target",
        "target-2",
        "action_type",
        "share-target",
        "category",
        "role_id",
        "type",
        "citation-id",
        "gap-citation-id",
    ],
)
def test_agent_strings_that_are_not_scenario_ids_never_reach_any_output(
    tmp_path: Path, change: Callable[[AgentDecision], Any]
) -> None:
    result = _run("telecom_operator", 0, change)
    _assert_absent(result, tmp_path)
    assert not any("FORGED" in line for line in format_result(result).splitlines())


def test_a_free_text_target_is_rejected_for_every_action() -> None:
    result = _run(
        "telecom_operator", 0, _action(action_type="investigate_network_fault", target=MARK)
    )
    rows = [e for e in result.log if e.action == "investigate_network_fault" and e.minute == 0]
    assert rows and all(e.kind == "rejected" and "unknown_target" in e.reasons for e in rows)


def _gap(statement: str) -> Callable[[AgentDecision], AgentDecision]:
    claim = GapClaim(
        statement=statement,
        citations=(Citation(clause_id="uae.fl2-2019.art2", relevance="r"),),
        qualification=GAP_QUALIFICATION,
    )
    return lambda d: d.model_copy(update={"gap_claims": (claim,)})


def test_a_gap_claim_finding_is_labelled_cited_and_qualified_everywhere(tmp_path: Path) -> None:
    forged = f"{MARK}\n  T+45 binding_legal_gap: FORGED engine finding"
    result = _run("policy_legal_adviser", 45, _gap(forged))
    gaps = [f for f in result.findings if f.kind == "candidate_gap_claim"]
    assert len(gaps) == 1
    assert gaps[0].detail.startswith(AGENT_STATEMENT) and "\n" not in gaps[0].detail
    assert gaps[0].detail.endswith(f"({GAP_QUALIFICATION})")
    assert gaps[0].clause_ids == ("uae.fl2-2019.art2",)
    out = _outputs(result, tmp_path)
    assert not any(line.lstrip().startswith("T+45 binding_legal_gap") for line in out["cli"])
    for where, lines in out.items():
        hits = [line for line in lines if "XYZZY" in line]
        assert hits and all(AGENT_STATEMENT in line for line in hits), where
    exported = [f for f in run_export(result)["findings"] if f["kind"] == "candidate_gap_claim"]
    assert exported[0]["qualification"] == GAP_QUALIFICATION
    assert exported[0]["clauses"] == [{"id": "uae.fl2-2019.art2", "status": "reviewed · binding"}]
    assert exported[0]["detail"] == gaps[0].detail


def test_a_multiline_rationale_is_stored_labelled_on_one_line(tmp_path: Path) -> None:
    result = _run(
        "telecom_operator", 0, lambda d: d.model_copy(update={"rationale": f"ok\n{MARK}"})
    )
    for where, lines in _outputs(result, tmp_path).items():
        assert all(AGENT_STATEMENT in line for line in lines if "XYZZY" in line), where
    stored = [e.detail for e in result.log if e.kind == "decision" and "XYZZY" in e.detail]
    assert stored == [f"{AGENT_STATEMENT}ok {MARK}"]


# ---- outside the pass scope, fixed on the human's request (2026-10-24) ----


@pytest.mark.parametrize("word", ["conclusively", "definitely", "absolutely"])
def test_a_gap_claim_stated_with_certainty_is_rejected(word: str) -> None:
    result = _run("policy_legal_adviser", 45, _gap(f"UAE law {word} leaves this duty unassigned"))
    assert not [f for f in result.findings if f.kind == "candidate_gap_claim"]
    assert [f for f in result.findings if f.kind == "overstated_gap_claim"]


def test_agent_output_type_is_checked_before_it_is_copied() -> None:
    ran: list[str] = []

    class Hostile:
        def __deepcopy__(self, memo: Any) -> Any:
            ran.append("deepcopy")
            return self

    result = _run("telecom_operator", 0, lambda d: Hostile())
    assert not ran
    assert [f for f in result.findings if f.kind == "malformed_decision" and f.minute == 0]


def test_a_foreign_object_inside_a_decision_runs_no_code() -> None:
    """Phase 4 round 1: an AgentDecision built with model_construct passes the type check; its
    fields are never deep-copied or repr'd."""
    ran: list[str] = []

    class Hostile:
        def __deepcopy__(self, memo: Any) -> Any:
            ran.append("deepcopy")
            return self

        def __repr__(self) -> str:
            ran.append("repr")
            raise ValueError(MARK)

    def nested(d: AgentDecision) -> AgentDecision:
        fields: dict[str, Any] = {**dict(d), "rationale": Hostile()}
        return AgentDecision.model_construct(**fields)

    result = _run("telecom_operator", 0, nested)
    assert not ran
    assert [f for f in result.findings if f.kind == "malformed_decision" and f.minute == 0]


@pytest.mark.parametrize("field", ["rationale", "gap"])
def test_control_characters_in_agent_text_never_reach_the_cli(field: str) -> None:
    text = "ok \x1b[1A\x1b[2K\u200b\u202e  T+45 binding_legal_gap: FORGED XYZZY"
    if field == "rationale":
        result = _run(
            "policy_legal_adviser", 45, lambda d: d.model_copy(update={"rationale": text})
        )
        stored = [e.detail for e in result.log if e.kind == "decision" and "XYZZY" in e.detail]
    else:
        result = _run("policy_legal_adviser", 45, _gap(text))
        stored = [f.detail for f in result.findings if "XYZZY" in f.detail]
    assert stored
    for out in (*stored, format_result(result)):
        assert not any(ch in out for ch in "\x1b\u200b\u202e")


def _nested_objects(ran: list[str]) -> list[object]:
    """Objects an agent could hide inside a model_construct decision (Phase 4 round 2)."""
    from dataclasses import dataclass
    from datetime import datetime, timedelta, tzinfo

    from pydantic import BaseModel, model_serializer

    class Serialised(BaseModel):
        @model_serializer
        def out(self) -> str:
            ran.append("model_serializer")
            return "fine text"

    def gen() -> Any:
        ran.append("generator body")
        yield "x"

    @dataclass
    class Sneaky:
        x: int = 0

        def __getattribute__(self, name: str) -> Any:
            ran.append("getattribute")
            return object.__getattribute__(self, name)

    class Zone(tzinfo):
        def utcoffset(self, dt: Any) -> timedelta:
            ran.append("utcoffset")
            return timedelta(hours=4)

    class Text(str):
        pass

    return [Serialised(), gen(), Sneaky(), datetime(2026, 1, 1, tzinfo=Zone()), Text("t")]


@pytest.mark.parametrize("index", range(5))
def test_no_nested_foreign_object_runs_code_or_passes(index: int) -> None:
    ran: list[str] = []
    obj = _nested_objects(ran)[index]
    field = "at" if index == 3 else "rationale"

    def nested(d: AgentDecision) -> AgentDecision:
        fields: dict[str, Any] = {**dict(d), field: obj}
        return AgentDecision.model_construct(**fields)

    result = _run("telecom_operator", 0, nested)
    assert not ran
    assert [f for f in result.findings if f.kind == "malformed_decision" and f.minute == 0]
