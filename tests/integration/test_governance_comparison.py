"""The ungoverned comparison run: its own expected output (never a golden), deterministic,
never the default, and refused where it could mislead or cost money."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

import cascadeguard.cli as cli
from cascadeguard.cli import load_world, main, run_scenario
from cascadeguard.engine.constraints import WAIVABLE, Governance
from cascadeguard.engine.governance import GovernanceComparison
from cascadeguard.storage.export import governance_markdown

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "uae_health_access"
EXPECTED = ROOT / "scenarios" / SCENARIO / "expected_ungoverned.yaml"
GOLDEN = ROOT / "scenarios" / SCENARIO / "expected_baseline.yaml"


def load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def comparison() -> GovernanceComparison:
    return load_world(SCENARIO).governance_comparison()


def test_ungoverned_run_reproduces_its_own_expected_output(
    comparison: GovernanceComparison,
) -> None:
    assert EXPECTED.read_text(encoding="utf-8").startswith(
        "# EXPECTED OUTPUT OF THE UNGOVERNED COMPARISON RUN (`--governance off`). NOT A GOLDEN."
    )
    assert comparison.ungoverned.summary() == load(EXPECTED)


def test_governed_run_is_unchanged_and_the_default(comparison: GovernanceComparison) -> None:
    assert comparison.governed.governance is Governance.ON
    assert comparison.governed.summary() == load(GOLDEN) == run_scenario(SCENARIO).summary()
    assert "governance" not in comparison.governed.summary()
    assert all(not e.waived for e in comparison.governed.log)


def test_the_cli_default_and_governance_on_print_the_same(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    outputs: list[tuple[str, str, str]] = []
    for extra in ([], ["--governance", "on"]):
        out_dir = tmp_path  # the same directory, so the printed export paths match
        assert main(["run", SCENARIO, "--export", str(out_dir), *extra]) == 0
        outputs.append(
            (
                capsys.readouterr().out,
                (out_dir / f"{SCENARIO}-baseline.json").read_text(encoding="utf-8"),
                (out_dir / f"{SCENARIO}-baseline.md").read_text(encoding="utf-8"),
            )
        )
    assert outputs[0] == outputs[1]
    assert "would have been rejected" not in outputs[0][0]


def test_the_ungoverned_run_is_deterministic(comparison: GovernanceComparison) -> None:
    again = load_world(SCENARIO).governance_comparison()
    assert again.ungoverned.summary() == comparison.ungoverned.summary()
    assert again.ungoverned.log == comparison.ungoverned.log
    assert governance_markdown(again) == governance_markdown(comparison)


def test_only_waivable_rejections_change(comparison: GovernanceComparison) -> None:
    waivable = {r.value for r in WAIVABLE}
    for e in comparison.ungoverned.log:
        if e.waived:
            assert e.kind == "accepted" and set(e.waived) <= waivable
        if e.kind == "rejected" and e.action is not None:
            assert not set(e.reasons) <= waivable  # a kept reason holds it back
    changed = comparison.changed_actions()
    assert changed and all(
        (a["governed"], a["ungoverned"]) == ("rejected", "accepted") for a in changed
    )
    assert len(changed) == len(comparison.waived())


def test_agents_see_the_same_views_until_a_waived_action_changes_the_state(
    comparison: GovernanceComparison,
) -> None:
    first = min(e.minute for e in comparison.ungoverned.log if e.waived)
    assert [v for v in comparison.governed.views if v.minute <= first] == [
        v for v in comparison.ungoverned.views if v.minute <= first
    ]
    # Later, only the role's own history differs, and only by its waived actions.
    waived = {(e.role, f"T+{e.minute} {e.action}") for e in comparison.ungoverned.log if e.waived}
    for on, off in zip(comparison.governed.views, comparison.ungoverned.views, strict=True):
        assert replace(on, own_history=()) == replace(off, own_history=())
        extra = set(off.own_history) - set(on.own_history)
        assert set(on.own_history) <= set(off.own_history)
        assert extra == {h for r, h in waived if r == off.role_id and off.minute > first}


def test_runs_must_be_given_in_order(comparison: GovernanceComparison) -> None:
    with pytest.raises(ValueError):
        GovernanceComparison(comparison.ungoverned, comparison.governed)
    for field, value in (("scenario_id", "other"), ("clause_set", "other"), ("agents", "other")):
        with pytest.raises(ValueError, match="same scenario"):
            GovernanceComparison(
                comparison.governed, replace(comparison.ungoverned, **{field: value})
            )


def test_repeated_proposals_are_compared_one_by_one() -> None:
    """Each repeat of an action is its own row, so changed actions match the waived ones."""
    from cascadeguard.agents.base import Agent
    from cascadeguard.domain.decisions import AgentDecision
    from cascadeguard.simulation.boundaries import RoleView
    from cascadeguard.simulation.orchestrator import run

    w = load_world(SCENARIO)
    inner = w.agents["health_service_operator"]

    class Repeats:
        role_id = "health_service_operator"

        def observe(self, view: RoleView) -> AgentDecision:
            d = inner.observe(view)
            if view.minute != 60:
                return d
            again = d.proposed_actions[:1] * 3  # reverse_automated_lockouts, three times
            return d.model_copy(update={"proposed_actions": (*again, *d.proposed_actions[1:])})

    agents: dict[str, Agent] = {**w.agents, "health_service_operator": Repeats()}
    runs = [
        run(w.scenario, w.roles, w.clauses, w.corpus_ids, agents, w.label, g)
        for g in (Governance.ON, Governance.OFF)
    ]
    c = GovernanceComparison(*runs)
    assert len(c.waived()) == 5
    assert len(c.changed_actions()) == len(c.waived())


def test_offline_llm_agents_build_no_client_and_say_when_not_comparable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Human decision 2026-10-31: LLM agents with --governance off only from the cache. With an
    empty cache no step has a decision, so the comparison is withheld; no client is built."""

    def no_client(*_: object, **__: object) -> None:
        raise AssertionError("no client may be built")

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("CASCADEGUARD_MODEL", "test/governance-no-such-model")
    monkeypatch.setattr("cascadeguard.agents.llm.ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setattr("cascadeguard.agents.llm.make_client", no_client)
    args = ["run", SCENARIO, "--governance", "off", "--agents", "llm", "--offline"]
    assert main([*args, "--cache", str(tmp_path / "cache")]) == 0
    out = capsys.readouterr().out
    assert "## Not comparable" in out
    assert "72 steps had no decision (36 in the governed run, 36 in the ungoverned run)" in out
    assert "0 steps reused, 72 not cached" in out


def test_cli_prints_and_exports_the_comparison(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["run", SCENARIO, "--governance", "off", "--export", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "**GOVERNANCE OFF: comparison only, not the governed result.**" in out
    assert "| patient_access_restored | unmet | met at T+60 |" in out
    assert "reverse_automated_lockouts: would have been rejected" in out
    assert "not a confirmed legal or standards gap" in out
    data = json.loads((tmp_path / f"{SCENARIO}-governance-off.json").read_text(encoding="utf-8"))
    assert data["ungoverned_run"]["governance"] == "off"
    assert "governance" not in data["governed_run"]
    md = (tmp_path / f"{SCENARIO}-governance-off.md").read_text(encoding="utf-8")
    assert out.startswith(md + "\n")  # the export is exactly what was printed


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--repair", "r1"], "drop --repair"),
        (["--audit"], "not recorded in the audit file"),
        (["--agents", "llm"], "add --offline"),
        (["--agents", "llm", "--cap", "1"], "add --offline"),
    ],
)
def test_refused_before_any_world_or_client_is_built(
    extra: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_world(*_: object, **__: object) -> None:
        raise AssertionError("load_world must not run")

    monkeypatch.setattr(cli, "load_world", no_world)
    assert main(["run", SCENARIO, "--governance", "off", *extra]) == 2
    assert message in capsys.readouterr().out


def test_repairs_has_no_governance_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["repairs", SCENARIO, "--governance", "off"])
    capsys.readouterr()


def test_ui_view_matches_the_comparison(comparison: GovernanceComparison) -> None:
    from cascadeguard.ui import view_model as vm

    v = vm.governance(comparison)
    assert ("patient_access_restored", "unmet", "met at T+60") in v.goals
    assert v.governed_raw == tuple(f.id for f in comparison.governed.failures)
    assert len(v.waived) == len(comparison.waived()) == 3
    assert all("would have been rejected (" in line for line in v.waived)
    assert sum(vm.CAUSE_STILL_PRESENT in r for r in v.ungoverned_raw) == len(comparison.masked())
    assert v.notes == comparison.notes() and not v.withheld
