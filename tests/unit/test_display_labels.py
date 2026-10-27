"""Display labels (spec 006b): UI-only display.yaml, plain-language repairs, names in rows.

Human decisions 2026-10-27: nothing outside `ui/` reads display.yaml; it is in no scenario hash
or manifest and the loader tolerates it; labels are pure renames.
"""

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from cascadeguard.agents.llm import render_view
from cascadeguard.cli import World, load_world, search_repairs
from cascadeguard.domain.repairs import RepairEdit, RepairOperationType
from cascadeguard.simulation.loader import SCENARIOS_DIR, load_scenario
from cascadeguard.simulation.replay import REPAIR_LABEL
from cascadeguard.storage.export import run_export, search_export
from cascadeguard.ui import app
from cascadeguard.ui import view_model as vm

SCENARIO = "uae_health_access"
SRC = Path(vm.__file__).resolve().parents[1]  # src/cascadeguard
HEALTH, TELECOM = "health_service_operator", "telecom_operator"


@pytest.fixture(scope="module")
def world() -> World:
    return load_world(SCENARIO)


@pytest.fixture(scope="module")
def labels(world: World) -> vm.Labels:
    return app.labels_for(world)


# --- 1.1 and 1.2: display.yaml is read by the UI only -------------------------------------


def test_no_module_outside_the_ui_reads_display_yaml() -> None:
    """Static: the file name, and the UI package, appear only in `ui/`."""
    for path in SRC.rglob("*.py"):
        if path.parent.name == "ui":
            continue
        text = path.read_text(encoding="utf-8")
        assert "display.yaml" not in text and "DISPLAY_FILE" not in text, path
        assert "cascadeguard.ui" not in text and "labels_for" not in text, path


def test_engine_agents_simulation_and_exports_ignore_display_yaml(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dynamic: with display.yaml replaced by unparseable text, the scenario still loads and the
    baseline, every agent view (so every LLM cache key), the search and the exports are
    identical. Only the UI's loader notices."""
    copy = tmp_path / SCENARIO
    shutil.copytree(SCENARIOS_DIR / SCENARIO, copy)
    (copy / app.DISPLAY_FILE).write_text("{ not: [valid yaml\n", encoding="utf-8")
    other = load_world(SCENARIO, scenarios_dir=tmp_path)
    load_scenario(SCENARIO, set(other.corpus_ids), tmp_path)  # tolerated, not read
    base, other_base = world.baseline(), other.baseline()
    assert run_export(other_base) == run_export(base)
    roles = tuple(r.id for r in world.roles.roles)
    assert [render_view(v, roles) for v in other_base.views] == [
        render_view(v, roles) for v in base.views
    ]
    found = search_repairs(SCENARIO, world=world)
    assert search_export(search_repairs(SCENARIO, world=other)) == search_export(found)
    monkeypatch.setattr(app, "SCENARIOS_DIR", tmp_path)
    with pytest.raises(yaml.YAMLError):
        app.labels_for(other)


# --- validation ------------------------------------------------------------------------------


def _write(tmp_path: Path, data: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / SCENARIO).mkdir(exist_ok=True)
    text = data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False)
    (tmp_path / SCENARIO / app.DISPLAY_FILE).write_text(text, encoding="utf-8")
    monkeypatch.setattr(app, "SCENARIOS_DIR", tmp_path)


def _real() -> dict[str, Any]:
    raw = (SCENARIOS_DIR / SCENARIO / app.DISPLAY_FILE).read_text(encoding="utf-8")
    return yaml.safe_load(raw)


def test_real_display_file_is_valid_and_complete(world: World, labels: vm.Labels) -> None:
    assert set(labels.actions) == {a.id for a in world.roles.actions}
    assert set(labels.goals) == {g.id for g in world.scenario.recovery_goals}
    assert set(labels.categories) >= world.roles.known_categories()
    # Role names are roles.yaml `name`, unchanged (human decision 2).
    assert labels.roles == {r.id: r.name for r in world.roles.roles}
    assert labels.role(HEALTH) == "Health Service Operator"
    assert labels.summary.startswith("Hypothetical scenario with synthetic data")


def test_missing_file_is_an_error_not_a_fallback(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / SCENARIO).mkdir()
    monkeypatch.setattr(app, "SCENARIOS_DIR", tmp_path)
    with pytest.raises(ValueError, match="missing"):
        app.labels_for(world)


DROP = object()  # remove the key


@pytest.mark.parametrize(
    ("section", "key", "value", "match"),
    [
        ("actions", "no_such_action", "X", r"unknown \['no_such_action'\]"),
        ("goals", "patient_access_restored", DROP, "patient_access_restored"),
        ("categories", "network_telemetry", 3, "network_telemetry"),
        ("categories", "network_telemetry", "two\nlines", "network_telemetry"),
        ("categories", "network_telemetry", "  ", "network_telemetry"),
        ("", "actions", ["a"], "not a mapping"),
        ("", "extra", {}, "expected incident_summary"),
        ("", "goals", DROP, "expected incident_summary"),
        ("", "incident_summary", "One. Two.", "one sentence"),
        ("", "incident_summary", "No full stop", "one sentence"),
        ("", "incident_summary", ["x."], "one sentence"),
        # review round 2 (test-breaker): every one of these was accepted before
        ("", "incident_summary", "Hypothetical.Second.", "one sentence"),
        ("", "incident_summary", "Is it a gap? Yes, it is.", "one sentence"),
        ("", "incident_summary", "Line one\rline two.", "one sentence"),
        ("", "incident_summary", "Line one\nline two.", "one sentence"),
        ("", "incident_summary", ".", "one sentence"),
        ("actions", "monitor", "Mon\ritor", "monitor"),
        ("actions", "monitor", "Mon\titor", "monitor"),
        ("actions", "monitor", "\u200b", "monitor"),  # invisible
        ("actions", "monitor", "  Monitor", "monitor"),
        ("actions", "monitor", "Monitor ", "monitor"),
        ("actions", "monitor", "suspend AI traffic model", "one label for several ids"),
    ],
)
def test_invalid_display_files_are_rejected(
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    key: str,
    value: object,
    match: str,
) -> None:
    data = _real()
    target: dict[str, Any] = data[section] if section else data
    if value is DROP:
        del target[key]
    else:
        target[key] = value
    _write(tmp_path, data, monkeypatch)
    with pytest.raises(ValueError, match=match):
        app.labels_for(world)


def test_not_a_mapping_is_rejected(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "- a list\n", monkeypatch)
    with pytest.raises(ValueError, match="expected incident_summary"):
        app.labels_for(world)


# --- plain-language repairs -----------------------------------------------------------------


EDITS: dict[RepairOperationType, tuple[dict[str, Any], str]] = {
    RepairOperationType.ASSIGN_OWNER: (
        {"action": "reverse_automated_lockouts"},
        "Assign reverse automated lockouts to Health Service Operator, 30-minute deadline",
    ),
    RepairOperationType.DEFINE_MINIMUM_DATA_SHARE: (
        {"data_category": "network_incident_status", "counterpart": HEALTH},
        "Allow Telecom Operator to share network incident status with Health Service Operator "
        "(minimum data share)",
    ),
    RepairOperationType.ADD_ESCALATION_TRIGGER: (
        {
            "action": "review_automated_lockouts",
            "trigger_event": "t45_responsibilities_diverge",
            "deadline_minutes": 15,
        },
        "Health Service Operator must review automated lockouts when “Institutional "
        "responsibilities diverge” (T+45), within 15 minutes",
    ),
    RepairOperationType.ADD_FALLBACK_CHANNEL: (
        {
            "action": "activate_fallback_channel",
            "trigger_event": "t60_public_access_affected",
            "deadline_minutes": 15,
        },
        "Health Service Operator must activate fallback channel when “Public access is "
        "affected” (T+60), within 15 minutes",
    ),
    RepairOperationType.DESIGNATE_DECISION_REQUESTER: (
        {
            "action": "activate_fallback_channel",
            "counterpart": "health_data_oversight",
            "trigger_event": "t60_public_access_affected",
            "deadline_minutes": 15,
        },
        "Health Service Operator requests a determination on activate fallback channel from "
        "Health-Data and Privacy Oversight when “Public access is affected” (T+60), "
        "within 15 minutes",
    ),
}


@pytest.mark.parametrize("op", list(RepairOperationType))
def test_one_sentence_per_operation_naming_every_parameter(
    op: RepairOperationType, labels: vm.Labels
) -> None:
    params, expected = EDITS[op]
    role = TELECOM if op is RepairOperationType.DEFINE_MINIMUM_DATA_SHARE else HEALTH
    edit = RepairEdit(operation=op, role=role, **params)
    sentence = vm.edit_sentence(edit, labels)
    assert sentence == expected
    assert labels.role(role) in sentence
    shown = {
        "action": vm.lower_first(labels.action(str(params.get("action", "")))),
        "data_category": vm.lower_first(labels.category(str(params.get("data_category", "")))),
        "counterpart": labels.role(str(params.get("counterpart", ""))),
        "trigger_event": labels.events.get(str(params.get("trigger_event", "")), (0, ""))[1],
        "deadline_minutes": str(edit.deadline_minutes),
    }
    for key in params:
        assert shown[key] in sentence, key
    if op is not RepairOperationType.DEFINE_MINIMUM_DATA_SHARE:  # every other one has a deadline
        assert f"{edit.deadline_minutes}" in sentence


def test_lower_first_keeps_a_leading_acronym() -> None:
    assert vm.lower_first("Reverse automated lockouts") == "reverse automated lockouts"
    assert vm.lower_first("AI traffic model") == "AI traffic model"


# --- names in rows; ids kept where they belong ------------------------------------------------


def test_rows_show_names_and_keep_ids(world: World, labels: vm.Labels) -> None:
    base = world.baseline()
    found = search_repairs(SCENARIO, world=world)
    rungs = vm.ladder(found, labels)
    assert rungs[0].roles == ("Health Service Operator", "Telecom Operator")
    assert rungs[0].sentences[0].startswith("Assign reverse automated lockouts")
    assert rungs[0].repair_id == found.ranked[0].proposal.repair_id  # the id stays, small print
    lanes = {lane.role: lane for lane in vm.swimlanes(base, world.scenario, labels)}
    assert lanes[HEALTH].name == "Health Service Operator"
    facts = [f for c in lanes[HEALTH].cells for f in c.facts]
    assert facts and all(f.label in labels.categories.values() for f in facts)
    assert all(f.text in {x.id for e in world.scenario.events for x in e.facts} for f in facts)
    acted = [c for c in lanes[HEALTH].cells if c.accepted or c.rejected]
    assert acted and all(c.raw for c in acted)  # raw ids for the tooltip and Expert mode
    assert any("raise_security_incident" in c.raw for c in acted)
    cards = {c.category: c for c in vm.diagnosis_cards(base, labels)}
    orphan = cards["orphan_duty"]
    assert orphan.title == "orphan duty"
    assert {i.title for i in orphan.items} == {
        "Reverse automated lockouts",
        "Activate fallback channel",
    }
    assert all(i.blocks == "Patient access restored" for i in orphan.items)
    deadlock = cards["information_deadlock"].items[0]
    assert deadlock.title == "Network incident status → Health Service Operator"
    # Clause chips keep their ids and status labels verbatim.
    assert all(ch.text in dict(base.loaded_clauses) for ch in deadlock.evidence)
    assert all(ch.label == dict(base.loaded_clauses)[ch.text] for ch in deadlock.evidence)
    v = vm.comparison(found.ranked[0], labels)
    assert ("Patient access restored", "unmet", "met at T+60") in v.goals
    assert all(e.endswith(f"[{REPAIR_LABEL}]") for e in v.edits)
    assert v.edit_ids == tuple(
        f"{e.operation.value} ({e.edit_id})" for e in found.ranked[0].proposal.edits
    )


def test_graph_names_tooltips_and_fading(world: World, labels: vm.Labels) -> None:
    base = world.baseline()
    failure = next(f.id for f in base.failures if f.id.startswith("orphan_duty:reverse"))
    option = vm.graph_option(base, failure, labels)
    nodes = {n["id"]: n for n in option["series"][0]["data"]}
    assert nodes["role:health_service_operator"]["name"] == "Health Service Operator"
    assert nodes["role:health_service_operator"]["value"] == HEALTH  # raw id in the tooltip
    assert nodes["action:reverse_automated_lockouts"]["name"] == "Reverse automated lockouts"
    clause = next(n for i, n in nodes.items() if i.startswith("clause:"))
    assert "[" in clause["name"]  # clause id with its status label, verbatim
    hot = {i for i, n in nodes.items() if n["symbolSize"] > 12}
    cold = set(nodes) - hot
    assert cold and all(nodes[i]["itemStyle"] == {"opacity": 0.15} for i in cold)
    assert all(not nodes[i]["label"]["show"] for i in cold)
    links = option["series"][0]["links"]
    assert all(x["lineStyle"] == {"opacity": 0.06} for x in links if "width" not in x["lineStyle"])
    shown = vm.graph_option(base, failure, labels, fade=False)
    flat = {n["id"]: n for n in shown["series"][0]["data"]}
    assert all(flat[i]["itemStyle"] == {} for i in cold)
    assert {i for i, n in flat.items() if n["symbolSize"] > 12} == hot  # same highlight


# --- review round 1 (Phase 6b) -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("monitor: Monitor\n", r"duplicate keys \['monitor'\]"),  # PyYAML would keep the last
        ("monitor: Suspend AI traffic model\n", "one label for several ids"),  # not a rename
        ("monitor: <b>Monitor</b>\n", r"missing or invalid \['monitor'\]"),  # markup
        ("monitor: Monitor [binding]\n", r"missing or invalid \['monitor'\]"),
    ],
)
def test_labels_are_unique_plain_renames(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, match: str
) -> None:
    raw = (SCENARIOS_DIR / SCENARIO / app.DISPLAY_FILE).read_text(encoding="utf-8")
    raw = raw.replace("  monitor: Monitor\n", "  monitor: Monitor\n  " + text, 1)
    if not text.startswith("monitor: Monitor\n"):  # replace the label instead of adding a key
        raw = raw.replace("  monitor: Monitor\n  " + text, "  " + text, 1)
    _write(tmp_path, raw, monkeypatch)
    with pytest.raises(ValueError, match=match):
        app.labels_for(world)


def test_all_diagnosed_failures_fades_nothing(world: World, labels: vm.Labels) -> None:
    base = world.baseline()
    option = vm.graph_option(base, None, labels)
    assert not [n for n in option["series"][0]["data"] if n["itemStyle"].get("opacity")]
    assert all(x["lineStyle"].get("opacity") != 0.06 for x in option["series"][0]["links"])


def test_graph_opens_on_the_first_diagnosis_card(world: World) -> None:
    base = world.baseline()
    first = next(i for c in vm.diagnosis_cards(base) for i in c.items)
    assert vm.default_failure(base) == first.id == "orphan_duty:activate_fallback_channel"


def test_split_screen_and_ladder_name_failures_and_label_every_sentence(
    world: World, labels: vm.Labels
) -> None:
    found = search_repairs(SCENARIO, world=world)
    v = vm.comparison(found.ranked[0], labels)
    assert len(v.baseline_named) == len(v.baseline_failures)
    assert len(v.replay_named) == len(v.removed) + len(v.replay_failures)
    assert "information deadlock: Network incident status → Health Service Operator" in (
        v.baseline_named
    )
    assert any(n.endswith(f": {vm.MASKED}") for n in v.replay_named)
    assert all(":" in n and "_" not in n.split(":", 1)[1] for n in v.baseline_named)
    verdict = vm.verdict(world.baseline(), found, world.scenario, labels)
    rungs = vm.ladder(found, labels)
    for sentence in (*verdict.sentences, *(x for r in rungs for x in r.sentences)):
        assert sentence.endswith(f"[{REPAIR_LABEL}]"), sentence
