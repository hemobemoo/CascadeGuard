"""The UI's view model: every label rule in specs/004-demo-ui.md, on the real run and on
hostile agent text. The page itself is checked end to end with Playwright."""

import json
import re
from dataclasses import replace
from typing import Any

import pytest

from cascadeguard.cli import World, load_world, search_repairs
from cascadeguard.domain.decisions import GAP_QUALIFICATION, AgentDecision, Citation, GapClaim
from cascadeguard.engine.constraints import AGENT_STATEMENT
from cascadeguard.engine.repair_search import (
    REMOVED_LABEL,
    SCRIPTED_LIMIT,
    SCRIPTED_LIMIT_NOTE,
    SearchResult,
)
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.replay import REPAIR_LABEL
from cascadeguard.storage.export import REPAIR_NOTE, SCRIPTED_NOTE
from cascadeguard.ui import app
from cascadeguard.ui import view_model as vm

SUCCESS = (
    "owner.reverse_automated_lockouts.health_service_operator"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)
MARK = "UAE law leaves this unassigned XYZZY"
CATEGORIES = load_world("uae_health_access").roles.known_categories()
CLAUSE = re.compile(
    r"\b((?:dha|uae|illus|eu|nist|oecd|itu|mocai|repair)\.[\w.+-]+)(?: \[([^\]]+)\])?"
)


@pytest.fixture(scope="module")
def world() -> World:
    return load_world("uae_health_access")


@pytest.fixture(scope="module")
def found() -> SearchResult:
    return search_repairs("uae_health_access")


def test_disclaimer_says_hypothetical_synthetic_and_not_legal_interpretation() -> None:
    for words in ("Hypothetical", "synthetic data", "decision support", "not legal"):
        assert words in vm.DISCLAIMER


def test_every_clause_carries_its_status_label_and_drafts_are_never_reviewed(
    world: World,
) -> None:
    b = world.baseline()
    rows = vm.clause_set(b, world.corpus_ids)
    labels = dict(b.loaded_clauses)
    for cid, label in b.loaded_clauses:
        assert f"{cid} [{label}]" in rows
        assert world.clauses[cid].status_label == label
    assert all(world.clauses[c].status.value != "draft" for c in labels)
    assert "draft clauses not loaded" in rows[-1]
    # A clause outside the loaded set is shown as "not loaded", never with another label.
    assert vm.cite(["dha.pp11.4-18-5"], labels) == "dha.pp11.4-18-5 [not loaded]"


def test_the_ui_records_exactly_the_views_the_agents_received(world: World) -> None:
    received: list[RoleView] = []

    def wrap(agent: Any) -> Any:
        class Recorder:
            def observe(self, view: RoleView) -> Any:
                received.append(view)
                return agent.observe(view)

        return Recorder()

    b = replace(world, agents={k: wrap(a) for k, a in world.agents.items()}).baseline()  # type: ignore[arg-type]
    assert list(b.views) == received
    assert len(b.views) == len(world.roles.roles) * len(world.scenario.events)


def test_role_views_show_only_what_the_role_could_see(world: World) -> None:
    b = world.baseline()
    for event in world.scenario.events:
        for role in world.roles.roles:
            v = vm.role_view(b, role.id, event.at_minute, CATEGORIES)
            assert set(v.inside).isdisjoint(v.outside)
            assert set(v.inside) == set(role.boundary.visible_categories)
            for fact in v.facts:
                category = fact.split(" (", 1)[1].split(",", 1)[0]
                assert category in v.inside
            assert v.recipient == (role.id in event.recipients)
            if not v.recipient:
                assert not v.description and not v.clauses
            assert all(s.startswith(AGENT_STATEMENT) for s in v.agent_statements)


def test_telecom_never_sees_patient_records(world: World) -> None:
    b = world.baseline()
    for event in world.scenario.events:
        v = vm.role_view(b, "telecom_operator", event.at_minute, CATEGORIES)
        assert "patient_account_records" in v.outside
        assert not any("patient_account_records" in f for f in v.facts)


def test_graph_highlights_the_selected_failure(world: World) -> None:
    b = world.baseline()
    failure = next(f for f in b.failures if f.id.startswith("orphan_duty:reverse"))
    option = vm.graph_option(b, failure.id)
    nodes = {n["id"]: n for n in option["series"][0]["data"]}
    hot = {i for i, n in nodes.items() if n["symbolSize"] > 12}
    assert "action:reverse_automated_lockouts" in hot
    assert {f"role:{r}" for r in failure.roles} <= hot
    assert hot <= set(nodes)
    # Only the selected failure: the deadlock's category is not highlighted for this one.
    assert "category:network_incident_status" not in hot
    other = vm.graph_option(b, next(f.id for f in b.failures if "deadlock" in f.id))
    other_hot = {n["id"] for n in other["series"][0]["data"] if n["symbolSize"] > 12}
    assert "action:reverse_automated_lockouts" not in other_hot
    red = [x for x in option["series"][0]["links"] if x["lineStyle"].get("width") == 3]
    assert red and all(
        "action:reverse_automated_lockouts" in (x["source"], x["target"]) for x in red
    )
    for n in nodes.values():  # clause nodes carry their status label
        if n["id"].startswith("clause:"):
            assert n["name"].endswith("]") and " [" in n["name"]


def test_repair_rows_show_masked_tags_and_authorization(found: SearchResult) -> None:
    rows = vm.repairs(found)
    assert rows[0].repair_id == SUCCESS
    assert rows[0].masked and all(m.endswith(vm.MASKED) for m in rows[0].masked)
    assert rows[0].authorization == vm.REQUIRES_AUTHORIZATION
    tagged = [c for r in rows for c in r.new_conflicts]
    assert tagged and all(f"scripted_agent_limit: {SCRIPTED_LIMIT_NOTE}" in c for c in tagged)
    assert all(not r.new_conflicts for r in rows if r.outcome != "introduces new conflict")
    assert vm.discarded(found) and all("[reviewed" in d for d in vm.discarded(found))


def test_comparison_labels_repair_rules_and_masked_blockers(found: SearchResult) -> None:
    v = vm.comparison(found.comparison(SUCCESS))
    assert v.edits and all(e.endswith(f"[{REPAIR_LABEL}]") for e in v.edits)
    assert v.authorization == vm.REQUIRES_AUTHORIZATION
    masked = [r for r in v.replay_failures if r.endswith(vm.MASKED)]
    assert len(masked) == 2
    assert not any("masked" in r for r in v.removed)
    assert ("patient_access_restored", "unmet", "met at T+60") in v.goals


def test_ui_exports_are_byte_identical_to_the_cli_exports(
    tmp_path: Any, world: World, found: SearchResult
) -> None:
    from cascadeguard.cli import main

    for argv in (["run"], ["repairs"], ["run", "--repair", SUCCESS]):
        assert main([argv[0], "uae_health_access", *argv[1:], "--export", str(tmp_path)]) == 0
    exported = vm.export_files(
        "uae_health_access", world.baseline(), found, found.comparison(SUCCESS)
    )
    assert len(exported) == 6
    for f in exported:
        assert (tmp_path / f.filename).read_text(encoding="utf-8") == f.content, f.filename


def test_exports_are_the_cli_exports_with_labels(world: World, found: SearchResult) -> None:
    b = world.baseline()
    exported = vm.export_files("uae_health_access", b, found, found.comparison(SUCCESS))
    files = {f.filename: f.content for f in exported}
    assert len(files) == 6 and len({f.label for f in exported}) == 6
    baseline = json.loads(files["uae_health_access-baseline.json"])
    assert all("status" in c for c in baseline["loaded_clauses"])
    assert vm.DISCLAIMER in files["uae_health_access-baseline.md"]
    replay = files[f"uae_health_access-replay-{SUCCESS}.md"]
    assert "Masked (goal met another way" in replay
    assert all(vm.DISCLAIMER in c for name, c in files.items() if name.endswith(".md"))


def test_hostile_agent_text_appears_only_labelled(world: World) -> None:
    claim = GapClaim(
        statement=f"{MARK}\nFORGED line",
        citations=(Citation(clause_id="uae.fl2-2019.art2", relevance="r"),),
        qualification=GAP_QUALIFICATION,
    )

    class Adviser:
        def observe(self, view: RoleView) -> AgentDecision:
            d = world.agents["policy_legal_adviser"].observe(view)
            if view.minute != 45:
                return d
            return d.model_copy(update={"rationale": MARK, "gap_claims": (claim,)})

    b = replace(world, agents={**world.agents, "policy_legal_adviser": Adviser()}).baseline()  # type: ignore[dict-item]
    shown = [
        *vm.role_view(b, "policy_legal_adviser", 45, CATEGORIES).agent_statements,
        *vm.findings(b),
        *(line for row in vm.timeline(b, world.scenario) for line in row.lines),
    ]
    hits = [s for s in shown if "XYZZY" in s]
    assert hits and all(AGENT_STATEMENT in s and "\n" not in s for s in hits)
    gap = next(s for s in vm.findings(b) if "candidate_gap_claim" in s)
    assert GAP_QUALIFICATION in gap and "uae.fl2-2019.art2 [reviewed]" in gap


def test_port_defaults_to_8765_and_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(app.PORT_VARIABLE, raising=False)
    assert app.port() == 8765
    monkeypatch.setenv(app.PORT_VARIABLE, "9123")
    assert app.port() == 9123


# ---- Phase 4 review round 3: one test per display path ----


def _assert_labelled(texts: list[str], labels: dict[str, str]) -> int:
    """Every clause id in the texts carries its loaded status label (or "not loaded")."""
    seen = 0
    for text in texts:
        for cid, label in CLAUSE.findall(text):
            if cid.startswith("repair."):
                continue
            assert label == labels.get(cid, "not loaded"), (cid, text)
            seen += 1
    return seen


def test_timeline_failures_and_role_view_clauses_carry_status_labels(world: World) -> None:
    b = world.baseline()
    labels = dict(b.loaded_clauses)
    timeline = [line for row in vm.timeline(b, world.scenario) for line in row.lines]
    assert _assert_labelled(timeline, labels)
    failure_clauses = [f.clauses for f in vm.failures(b)]
    assert _assert_labelled(failure_clauses, labels)
    shown = [
        c
        for e in world.scenario.events
        for r in world.roles.roles
        for c in vm.role_view(b, r.id, e.at_minute, CATEGORIES).clauses
    ]
    assert _assert_labelled(shown, labels)


def test_failure_rows_keep_the_engine_qualification(world: World) -> None:
    b = world.baseline()
    rows = vm.failures(b)
    assert [r.qualification for r in rows] == [f.qualification for f in b.failures]
    assert all(r.qualification for r in rows)


def test_comparison_labels_targets_removed_tags_and_notes(found: SearchResult) -> None:
    success = vm.comparison(found.comparison(SUCCESS))
    assert success.notes == (REPAIR_NOTE, SCRIPTED_NOTE)
    assert success.removed and all(r.endswith(f": {REMOVED_LABEL}") for r in success.removed)
    tagged = next(c for c in found.ranked if c.conflict_tags())
    v = vm.comparison(tagged)
    new = [r for r in v.replay_failures if "NEW conflict" in r]
    assert new and all(f"[{SCRIPTED_LIMIT}: {SCRIPTED_LIMIT_NOTE}]" in r for r in new)
    labels = dict(tagged.replay.loaded_clauses)
    if tagged.proposal.citations:
        assert _assert_labelled([v.targets], labels)
    for c in found.ranked:  # every target list is labelled
        _assert_labelled([vm.comparison(c).targets], dict(c.replay.loaded_clauses))


def test_role_view_shows_only_its_own_role_and_the_whole_view(world: World) -> None:
    def marked(role: str) -> Any:
        agent = world.agents[role]

        class Agent:
            def observe(self, view: RoleView) -> AgentDecision:
                return agent.observe(view).model_copy(update={"rationale": f"MARK-{role}"})

        return Agent()

    b = replace(world, agents={r: marked(r) for r in world.agents}).baseline()  # type: ignore[arg-type]
    for event in world.scenario.events:
        for role in world.roles.roles:
            v = vm.role_view(b, role.id, event.at_minute, CATEGORIES)
            for s in v.agent_statements:
                assert s == f"{AGENT_STATEMENT}MARK-{role.id}"
            received = next(
                x for x in b.views if x.role_id == role.id and x.minute == event.at_minute
            )
            assert v.instructions == received.instructions
            assert v.allowed_actions == received.allowed_actions
            assert v.at == received.at.isoformat()
            assert set(v.outside) == set(CATEGORIES) - set(v.inside)
