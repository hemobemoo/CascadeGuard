"""LLM agents without the network: a fake client returns recorded replies (specs/005).

The fake records every request, so the tests check what would be sent (settings, no response
healing) and how many calls a run or a replay makes.
"""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest

from cascadeguard.agents.cache import DecisionCache, cache_key, model_digest
from cascadeguard.agents.llm import (
    AGENT_FILLED,
    PROMPT_VERSION,
    LLMAgent,
    LLMConfig,
    LLMConfigError,
    LLMDecisionPayload,
    build_messages,
    response_schema,
)
from cascadeguard.agents.scripted import ScriptedAgent
from cascadeguard.cli import World, load_world, main, search_repairs
from cascadeguard.domain.decisions import AgentDecision, ProposedAction
from cascadeguard.engine.constraints import WITHHELD, Reason
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.orchestrator import run
from cascadeguard.simulation.replay import replay

SCENARIO = "uae_health_access"
MODEL = "test/fake-model"  # never a real model id; tests make no calls
SUCCESS = (
    "owner.reverse_automated_lockouts.health_service_operator"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)

Reply = Callable[[dict[str, Any]], str | Exception]
TextReply = Callable[[dict[str, Any]], str]


class FakeClient:
    """Stands in for openai.OpenAI: `chat.completions.create(**request)`."""

    def __init__(self, reply: Reply) -> None:
        self.reply = reply
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request: Any) -> Any:
        self.requests.append(request)
        out = self.reply(request)
        if isinstance(out, Exception):
            raise out
        usage = SimpleNamespace(
            prompt_tokens=100, completion_tokens=20, model_extra={"cost": 0.001}
        )
        message = SimpleNamespace(content=out)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def payload_of(decision: AgentDecision) -> str:
    """A recorded reply: the decision as the model would send it (schema shape)."""
    return json.dumps(
        {
            "proposed_actions": [
                {
                    "action_type": a.action_type,
                    "target": a.target,
                    "parameters": [{"name": k, "value": v} for k, v in a.parameters.items()],
                }
                for a in decision.proposed_actions
            ],
            "rationale": decision.rationale,
            "citations": [c.model_dump() for c in decision.citations],
            "uncertainty": list(decision.uncertainty),
            "gap_claims": [g.model_dump() for g in decision.gap_claims],
        }
    )


def view_of(request: dict[str, Any]) -> dict[str, Any]:
    return json.loads(request["messages"][1]["content"])


@pytest.fixture(scope="module")
def scripted() -> World:
    return load_world(SCENARIO)


def scripted_replies(world: World) -> TextReply:
    """Replays the scripted decisions as model replies, keyed by role and minute."""
    agents = world.agents

    def reply(request: dict[str, Any]) -> str:
        v = view_of(request)
        agent = agents[v["role_id"]]
        assert isinstance(agent, ScriptedAgent)
        decision = agent.observe(_stub_view(world, v["role_id"], v["minute"]))
        return payload_of(decision)

    return reply


def _stub_view(world: World, role: str, minute: int) -> RoleView:
    # ScriptedAgent reads only role, minute and time from the view.
    base = world.baseline().views
    return next(v for v in base if v.role_id == role and v.minute == minute)


def llm_world(world: World, client: FakeClient | None, cache: DecisionCache) -> World:
    role_ids = tuple(r.id for r in world.roles.roles)
    agents = {r: LLMAgent(r, MODEL, client, cache, role_ids) for r in role_ids}
    return replace(world, agents=dict(agents), cache=cache)


# --- Request and schema ---------------------------------------------------------------------


def test_request_carries_the_required_openrouter_settings(scripted: World, tmp_path: Path) -> None:
    client = FakeClient(scripted_replies(scripted))
    view = scripted.baseline().views[0]
    LLMAgent(view.role_id, MODEL, client, DecisionCache(tmp_path), ()).observe(view)
    (req,) = client.requests
    assert req["model"] == MODEL
    assert req["temperature"] == 0
    fmt = req["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == response_schema()
    assert req["extra_body"]["provider"] == {"require_parameters": True}
    assert req["extra_body"]["reasoning"] == {"enabled": False}
    # Response healing is explicitly off; no plugin is switched on.
    assert req["extra_body"]["plugins"] == [{"id": "response-healing", "enabled": False}]
    assert all(p.get("enabled") is False for p in req["extra_body"]["plugins"])


def test_payload_is_agent_decision_without_the_agent_filled_fields() -> None:
    assert set(LLMDecisionPayload.model_fields) == set(AgentDecision.model_fields) - AGENT_FILLED
    for name in ("rationale", "citations", "uncertainty", "gap_claims"):
        assert (
            LLMDecisionPayload.model_fields[name].annotation
            == AgentDecision.model_fields[name].annotation
        )


def test_schema_is_strict_everywhere() -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node = cast(dict[str, Any], node)
            assert "default" not in node and "const" not in node
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert sorted(node["required"]) == sorted(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in cast(list[Any], node):
                walk(v)

    walk(response_schema())


def test_prompt_holds_only_the_view(scripted: World) -> None:
    """The prompt is built from the role's own view: no other role's facts reach it."""
    b = scripted.baseline()
    for v in b.views:
        text = build_messages(v, ())[1]["content"]
        others = {f.id for o in b.views if o.role_id != v.role_id for f in o.facts} - {
            f.id for f in v.facts
        }
        for fact_id in others:
            assert f'"{fact_id}"' not in text, (v.role_id, v.minute, fact_id)


# --- Runs ---------------------------------------------------------------------------------


def test_llm_run_completes_and_matches_scripted_when_replies_match(
    scripted: World, tmp_path: Path
) -> None:
    client = FakeClient(scripted_replies(scripted))
    w = llm_world(scripted, client, DecisionCache(tmp_path))
    result = w.baseline()
    assert len(client.requests) == len(result.views) == 36
    assert not result.scripted
    assert result.summary() == scripted.baseline().summary()


def test_unknown_citation_is_rejected_as_a_finding(scripted: World, tmp_path: Path) -> None:
    base = scripted_replies(scripted)

    def reply(request: dict[str, Any]) -> str:
        v = view_of(request)
        out = json.loads(base(request))
        if v["role_id"] == "health_service_operator" and v["minute"] == 15:
            out["citations"].append({"clause_id": "uae.invented.art99", "relevance": "x"})
        return json.dumps(out)

    result = llm_world(scripted, FakeClient(reply), DecisionCache(tmp_path)).baseline()
    found = [f for f in result.findings if f.kind == Reason.UNKNOWN_CITATION.value]
    assert [(f.minute, f.role, f.clause_ids) for f in found] == [
        (15, "health_service_operator", (WITHHELD,))
    ]
    assert not any(
        e.kind == "accepted" and e.role == "health_service_operator" and e.minute == 15
        for e in result.log
    )


def test_invalid_output_is_retried_once(scripted: World, tmp_path: Path) -> None:
    base = scripted_replies(scripted)
    seen: set[tuple[str, int]] = set()

    def reply(request: dict[str, Any]) -> str:
        v = view_of(request)
        if (v["role_id"], v["minute"]) not in seen:
            seen.add((v["role_id"], v["minute"]))
            return "{not json"
        return base(request)

    client = FakeClient(reply)
    result = llm_world(scripted, client, DecisionCache(tmp_path)).baseline()
    assert len(client.requests) == 72  # every step: one bad reply, one retry
    assert result.summary() == scripted.baseline().summary()


def test_invalid_twice_is_a_no_decision_finding_and_cached(scripted: World, tmp_path: Path) -> None:
    base = scripted_replies(scripted)

    def reply(request: dict[str, Any]) -> str:
        v = view_of(request)
        if v["role_id"] == "telecom_operator" and v["minute"] == 0:
            return json.dumps({"proposed_actions": "nope"})  # schema mismatch
        return base(request)

    cache = DecisionCache(tmp_path)
    client = FakeClient(reply)
    result = llm_world(scripted, client, cache).baseline()
    found = [f for f in result.findings if f.kind == Reason.NO_DECISION.value]
    assert [(f.minute, f.role) for f in found] == [(0, "telecom_operator")]
    assert "invalid_output" in found[0].detail and "nope" not in found[0].detail
    assert len(client.requests) == 37
    # A second run is the identical incident from the cache: no calls, same findings.
    again = FakeClient(reply)
    rerun = llm_world(scripted, again, DecisionCache(tmp_path)).baseline()
    assert not again.requests
    assert rerun.summary() == result.summary()


def test_request_errors_are_retried_then_not_cached(scripted: World, tmp_path: Path) -> None:
    client = FakeClient(lambda _: ConnectionError("down"))
    view = scripted.baseline().views[0]
    cache = DecisionCache(tmp_path)
    decision = LLMAgent(view.role_id, MODEL, client, cache, ()).observe(view)
    assert decision.no_decision == "request_failed"
    assert len(client.requests) == 2
    assert not list(tmp_path.glob("*.json"))


def test_offline_miss_is_not_cached_no_decision(scripted: World, tmp_path: Path) -> None:
    result = llm_world(scripted, None, DecisionCache(tmp_path)).baseline()
    kinds = {f.kind for f in result.findings}
    assert Reason.NO_DECISION.value in kinds
    assert all(
        "not_cached" in f.detail for f in result.findings if f.kind == Reason.NO_DECISION.value
    )


def test_replay_reuses_cached_decisions_for_unchanged_steps(
    scripted: World, tmp_path: Path
) -> None:
    client = FakeClient(scripted_replies(scripted))
    cache = DecisionCache(tmp_path)
    w = llm_world(scripted, client, cache)
    base = run(w.scenario, w.roles, w.clauses, w.corpus_ids, w.agents, w.label)
    assert len(client.requests) == 36 and cache.stats.hits == 0
    proposal = search_repairs(SCENARIO).comparison(SUCCESS).proposal
    before_calls, before_hits = len(client.requests), cache.stats.hits
    rep = replay(w.scenario, w.roles, w.clauses, w.corpus_ids, w.agents, w.label, proposal)
    calls = len(client.requests) - before_calls
    hits = cache.stats.hits - before_hits
    schema = response_schema()

    def key(v: RoleView) -> str:
        return cache_key(v.role_id, v, PROMPT_VERSION, MODEL, schema)

    base_keys = {key(v) for v in base.views}
    unchanged = [v for v in rep.views if key(v) in base_keys]
    changed = [v for v in rep.views if key(v) not in base_keys]
    assert unchanged and changed  # the repair changes some views, not all
    assert hits == len(unchanged)  # every unchanged step came from the cache
    assert calls == len(changed)  # and only changed steps made a call
    asked = {(view_of(r)["role_id"], view_of(r)["minute"]) for r in client.requests[36:]}
    assert asked == {(v.role_id, v.minute) for v in changed}


def test_cache_key_depends_on_model_prompt_and_view(scripted: World) -> None:
    v0, v1 = scripted.baseline().views[:2]
    schema = response_schema()
    k = cache_key(v0.role_id, v0, PROMPT_VERSION, MODEL, schema)
    assert k == cache_key(v0.role_id, v0, PROMPT_VERSION, MODEL, schema)
    assert k != cache_key(v0.role_id, v0, PROMPT_VERSION, MODEL + "-other", schema)
    assert k != cache_key(v0.role_id, v0, PROMPT_VERSION + "x", MODEL, schema)
    assert k != cache_key(v1.role_id, v1, PROMPT_VERSION, MODEL, schema)


def test_cache_files_hold_no_model_id(scripted: World, tmp_path: Path) -> None:
    client = FakeClient(scripted_replies(scripted))
    view = scripted.baseline().views[0]
    LLMAgent(view.role_id, MODEL, client, DecisionCache(tmp_path), ()).observe(view)
    (path,) = tmp_path.glob("*.json")
    text = path.read_text(encoding="utf-8")
    assert MODEL not in text and model_digest(MODEL) in text


def test_no_decision_cannot_carry_actions(scripted: World) -> None:
    view = scripted.baseline().views[0]
    with pytest.raises(ValueError, match="no-decision"):
        AgentDecision.model_validate(
            {
                "role_id": view.role_id,
                "at": view.at,
                "proposed_actions": [{"action_type": "monitor"}],
                "rationale": "",
                "citations": [],
                "uncertainty": [],
                "no_decision": "invalid_output",
            }
        )


# --- Configuration and CLI ------------------------------------------------------------------


def test_missing_configuration_names_variables_not_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "CASCADEGUARD_MODEL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-secret-value-123\n", encoding="utf-8")
    with pytest.raises(LLMConfigError) as err:
        LLMConfig.from_env(env)
    message = str(err.value)
    assert "OPENROUTER_BASE_URL" in message and "CASCADEGUARD_MODEL" in message
    assert "sk-secret" not in message and "OPENROUTER_API_KEY" not in message
    with pytest.raises(LLMConfigError):
        LLMConfig.model_from_env(env)
    env.write_text(env.read_text() + "OPENROUTER_BASE_URL=u\nCASCADEGUARD_MODEL=m\n")
    config = LLMConfig.from_env(env)
    assert "sk-secret" not in repr(config)


def test_cli_offline_llm_run_needs_no_key_and_prints_no_model(
    scripted: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Fill a cache through the fake client, then run the CLI offline from it.
    llm_world(scripted, FakeClient(scripted_replies(scripted)), DecisionCache(tmp_path)).baseline()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("CASCADEGUARD_MODEL", MODEL)
    monkeypatch.setattr("cascadeguard.agents.llm.ENV_FILE", tmp_path / "absent.env")
    code = main(["run", SCENARIO, "--agents", "llm", "--offline", "--cache", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert (
        "Agents: LLM agents (model from CASCADEGUARD_MODEL; output mode json_schema; offline" in out
    )
    assert "LLM decision cache (baseline and replays): 36 steps reused, 0 not cached" in out
    assert MODEL not in out
    assert "no_decision" not in out


def test_cli_llm_without_configuration_fails_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "CASCADEGUARD_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("cascadeguard.agents.llm.ENV_FILE", tmp_path / "absent.env")
    assert main(["run", SCENARIO, "--agents", "llm", "--cache", str(tmp_path)]) == 2
    assert "no default model is used" in capsys.readouterr().out


def test_scripted_is_still_the_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", SCENARIO]) == 0
    out = capsys.readouterr().out
    assert "Agents: scripted agents (scripted_decisions.yaml)" in out  # every output names them
    assert "LLM" not in out and "LLM decision cache" not in out


# --- Review round 2 (test-breaker on 7eaf00b) -------------------------------------------------


def test_request_failure_is_the_same_outcome_in_every_run_of_a_family(
    scripted: World, tmp_path: Path
) -> None:
    """A step that failed in the baseline fails the same way in a replay with the same view: it
    is never re-asked and credited to the repair (BLOCKER, round 2)."""
    base = scripted_replies(scripted)
    failures = {"left": 2}

    def reply(request: dict[str, Any]) -> str | Exception:
        v = view_of(request)
        if (v["role_id"], v["minute"]) == ("health_data_oversight", 60) and failures["left"]:
            failures["left"] -= 1
            return ConnectionError("transient")
        return base(request)

    cache = DecisionCache(tmp_path)
    w = llm_world(scripted, FakeClient(reply), cache)
    shown = w.baseline()
    found = search_repairs(SCENARIO, world=w)
    c = found.comparison(SUCCESS)
    schema = response_schema()

    def key(v: RoleView) -> str:
        return cache_key(v.role_id, v, PROMPT_VERSION, MODEL, schema)

    def entries(result: Any, role: str, minute: int) -> list[tuple[Any, ...]]:
        return [
            (e.kind, e.action, e.reasons)
            for e in result.log
            if e.role == role and e.minute == minute and e.kind in ("accepted", "rejected")
        ]

    base_keys = {(v.role_id, v.minute): key(v) for v in c.baseline.views}
    step = ("health_data_oversight", 60)
    assert entries(shown, *step) == [("rejected", None, ("no_decision",))]
    assert shown.summary() == c.baseline.summary()  # the baseline shown is the one compared
    unchanged = [v for v in c.replay.views if base_keys[(v.role_id, v.minute)] == key(v)]
    assert step in {(v.role_id, v.minute) for v in unchanged}
    for v in unchanged:
        assert entries(c.baseline, v.role_id, v.minute) == entries(c.replay, v.role_id, v.minute)
    assert not list(tmp_path.glob(f"{base_keys[step]}.json"))  # still never written to disk


def test_exports_name_the_agents(scripted: World, tmp_path: Path) -> None:
    from cascadeguard.cli import baseline_markdown
    from cascadeguard.storage.export import comparison_export, comparison_markdown, run_export

    label = "LLM agents (model from CASCADEGUARD_MODEL; test)"
    w = replace(
        llm_world(scripted, FakeClient(scripted_replies(scripted)), DecisionCache(tmp_path)),
        agent_label=label,
    )
    result = w.baseline()
    assert run_export(result)["agents"] == label
    assert f"Agents: {label}" in baseline_markdown(SCENARIO, result, None)
    found = search_repairs(SCENARIO, world=w)
    assert found.agents == label
    c = found.comparison(SUCCESS)
    assert comparison_export(c)["agents"] == label
    assert f"- Agents: {label}" in comparison_markdown(c)
    assert run_export(scripted.baseline())["agents"].startswith("scripted agents")


def test_duplicate_parameter_names_are_rejected_not_collapsed(
    scripted: World, tmp_path: Path
) -> None:
    def reply(request: dict[str, Any]) -> str:
        return json.dumps(
            {
                "proposed_actions": [
                    {
                        "action_type": "share_incident_status",
                        "target": "telecom_regulator",
                        "parameters": [
                            {"name": "fact", "value": "first"},
                            {"name": "fact", "value": "second"},
                        ],
                    }
                ],
                "rationale": "",
                "citations": [],
                "uncertainty": [],
                "gap_claims": [],
            }
        )

    client = FakeClient(reply)
    view = scripted.baseline().views[0]
    decision = LLMAgent(view.role_id, MODEL, client, DecisionCache(tmp_path), ()).observe(view)
    assert decision.no_decision == "invalid_output"
    assert len(client.requests) == 2  # retried once, then rejected


def test_untrusted_cache_file_is_a_miss_not_a_crash(scripted: World, tmp_path: Path) -> None:
    llm_world(scripted, FakeClient(scripted_replies(scripted)), DecisionCache(tmp_path)).baseline()
    first, second, third = sorted(tmp_path.glob("*.json"))[:3]
    second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")  # copied entry
    third.write_text("{not json", encoding="utf-8")
    cache = DecisionCache(tmp_path)
    result = llm_world(scripted, None, cache).baseline()  # offline: no call possible
    # The two untrusted steps miss; their no-decision then changes later views, which miss too.
    assert cache.stats.untrusted == 2 and cache.stats.misses >= 2
    missed = [f for f in result.findings if f.kind == Reason.NO_DECISION.value]
    assert len(missed) == cache.stats.misses and all("not_cached" in f.detail for f in missed)


# --- Review round 3 (test-breaker on 5192248) -------------------------------------------------


def test_live_search_is_refused_by_the_world_in_use(
    scripted: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guard looks at the agents a world holds, never at a toggle (MAJOR, round 3)."""
    from cascadeguard import cli

    client = FakeClient(scripted_replies(scripted))
    live = llm_world(scripted, client, DecisionCache(tmp_path))
    assert cli.live_llm(live)
    assert not cli.live_llm(llm_world(scripted, None, DecisionCache(tmp_path)))
    assert not cli.live_llm(scripted)

    def fake_load(*_: Any, **__: Any) -> World:
        return live

    monkeypatch.setattr(cli, "load_world", fake_load)
    # A live search is refused; a live single replay has its own guard (P5-6 tests below).
    assert main(["repairs", SCENARIO, "--agents", "llm"]) == 2
    assert "repair search with live LLM calls is not enabled" in capsys.readouterr().out
    assert not client.requests  # refused before any call


def test_inconsistent_or_stored_failure_cache_entries_are_not_trusted(
    scripted: World, tmp_path: Path
) -> None:
    llm_world(scripted, FakeClient(scripted_replies(scripted)), DecisionCache(tmp_path)).baseline()
    files = sorted(tmp_path.glob("*.json"))[:3]
    edits = (
        {"outcome": "decision", "decision": None, "no_decision": None},
        {"outcome": "no_decision", "no_decision": "invalid_output"},  # decision still present
        {"outcome": "no_decision", "decision": None, "no_decision": "request_failed"},
    )
    for path, edit in zip(files, edits, strict=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, **edit}), encoding="utf-8")
    cache = DecisionCache(tmp_path)
    llm_world(scripted, None, cache).baseline()  # completes: no crash
    assert cache.stats.untrusted == 3


def test_repeated_request_failures_are_not_counted_as_reused(
    scripted: World, tmp_path: Path
) -> None:
    from cascadeguard.cli import cache_line

    cache = DecisionCache(tmp_path)
    w = llm_world(scripted, FakeClient(lambda _: ConnectionError("down")), cache)
    w.baseline()
    w.baseline()
    assert cache.stats.hits == 0 and cache.stats.failures_repeated > 0
    line = cache_line(w)
    assert line is not None and "0 steps reused" in line and "repeated an earlier request" in line


def test_search_export_and_audit_name_the_agents(scripted: World, tmp_path: Path) -> None:
    import duckdb

    from cascadeguard.storage.audit import AuditStore
    from cascadeguard.storage.export import search_export

    label = "LLM agents (model from CASCADEGUARD_MODEL; test)"
    w = replace(
        llm_world(scripted, FakeClient(scripted_replies(scripted)), DecisionCache(tmp_path)),
        agent_label=label,
    )
    found = search_repairs(SCENARIO, world=w)
    assert search_export(found)["agents"] == label
    db = tmp_path / "audit.duckdb"
    store = AuditStore(db)
    try:
        run_id = store.record_run(w.baseline(), "baseline")
    finally:
        store.close()
    con = duckdb.connect(str(db), read_only=True)
    try:
        row = con.execute("SELECT summary FROM runs WHERE run_id = ?", [run_id]).fetchone()
    finally:
        con.close()
    assert row is not None and json.loads(row[0])["agents"] == label


# --- Output mode (human decision 2026-10-24: explicit JSON-mode fallback) ---------------------


def test_json_object_mode_sends_json_mode_with_the_schema_in_the_prompt(
    scripted: World, tmp_path: Path
) -> None:
    from cascadeguard.agents.llm import SYSTEM_PROMPT

    client = FakeClient(scripted_replies(scripted))
    view = scripted.baseline().views[0]
    agent = LLMAgent(
        view.role_id, MODEL, client, DecisionCache(tmp_path), (), output_mode="json_object"
    )
    decision = agent.observe(view)
    (req,) = client.requests
    assert req["response_format"] == {"type": "json_object"}
    assert req["temperature"] == 0
    assert req["extra_body"]["provider"] == {"require_parameters": True}
    assert req["extra_body"]["reasoning"] == {"enabled": False}
    assert req["extra_body"]["plugins"] == [{"id": "response-healing", "enabled": False}]
    system = req["messages"][0]["content"]
    assert system.startswith(SYSTEM_PROMPT)
    assert json.dumps(response_schema(), ensure_ascii=False, sort_keys=True) in system
    assert not {"role_id", "at"} & set(response_schema()["properties"])  # filled in by code
    assert decision.no_decision is None and decision.role_id == view.role_id


def test_json_object_mode_validates_the_same_way(scripted: World, tmp_path: Path) -> None:
    """No repair in JSON mode either: prose around the JSON, or a schema mismatch, is invalid."""
    replies = iter(["Here you go: {}", json.dumps({"proposed_actions": []})])
    client = FakeClient(lambda _: next(replies))
    view = scripted.baseline().views[0]
    agent = LLMAgent(
        view.role_id, MODEL, client, DecisionCache(tmp_path), (), output_mode="json_object"
    )
    assert agent.observe(view).no_decision == "invalid_output"
    assert len(client.requests) == 2


def test_output_mode_enters_the_cache_key(scripted: World, tmp_path: Path) -> None:
    view = scripted.baseline().views[0]
    cache = DecisionCache(tmp_path)
    schema_agent = LLMAgent(view.role_id, MODEL, FakeClient(scripted_replies(scripted)), cache, ())
    json_agent = LLMAgent(
        view.role_id,
        MODEL,
        FakeClient(scripted_replies(scripted)),
        cache,
        (),
        output_mode="json_object",
    )
    assert schema_agent.prompt_version != json_agent.prompt_version
    schema_agent.observe(view)
    json_agent.observe(view)
    assert len(list(tmp_path.glob("*.json"))) == 2  # one entry per mode, never shared


def test_output_mode_setting_is_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("CASCADEGUARD_OUTPUT_MODE=json_object" + chr(10), encoding="utf-8")
    assert LLMConfig.output_mode_from_env(env) == "json_object"
    assert LLMConfig.output_mode_from_env(tmp_path / "absent.env") == "json_schema"
    monkeypatch.setenv("CASCADEGUARD_OUTPUT_MODE", "auto-fallback")
    with pytest.raises(LLMConfigError) as err:
        LLMConfig.output_mode_from_env(env)
    assert "auto-fallback" not in str(err.value)
    with pytest.raises(ValueError):
        LLMAgent("r", MODEL, None, DecisionCache(tmp_path), (), output_mode="text")


# --- P5-6: single-repair replay with LLM agents -----------------------------------------------


def _patch_world(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    from cascadeguard import cli

    def fake_load(*_: Any, **__: Any) -> World:
        return world

    monkeypatch.setattr(cli, "load_world", fake_load)


def test_single_repair_live_replay_needs_the_flag_and_prints_the_estimate(
    scripted: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(scripted_replies(scripted))
    live = llm_world(scripted, client, DecisionCache(tmp_path))
    live.baseline()  # the approved baseline, now cached
    assert len(client.requests) == 36
    _patch_world(monkeypatch, live)
    argv = ["run", SCENARIO, "--repair", SUCCESS, "--agents", "llm"]
    assert main(argv) == 2
    out = capsys.readouterr().out
    assert "needs --live" in out
    estimate = int(out.split("Uncached steps (dry run from the cache): ")[1].split()[0])
    assert estimate > 0
    assert len(client.requests) == 36  # the estimate made no call
    # With --live: exactly the one repair is replayed, never the whole search.
    fresh = llm_world(scripted, client, DecisionCache(tmp_path))
    _patch_world(monkeypatch, fresh)
    assert main([*argv, "--live"]) == 0
    out = capsys.readouterr().out
    assert f"# Replay: {SUCCESS}" in out
    assert len(client.requests) - 36 == estimate  # deterministic replies: estimate is exact


def test_single_repair_live_replay_refused_without_a_cached_baseline(
    scripted: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(scripted_replies(scripted))
    _patch_world(monkeypatch, llm_world(scripted, client, DecisionCache(tmp_path)))
    argv = ["run", SCENARIO, "--repair", SUCCESS, "--agents", "llm", "--live"]
    assert main(argv) == 2
    assert "baseline is not fully cached (36 steps)" in capsys.readouterr().out
    assert not client.requests


def test_single_repair_offline_replays_only_that_repair(
    scripted: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascadeguard import cli

    filler = FakeClient(scripted_replies(scripted))
    llm_world(scripted, filler, DecisionCache(tmp_path)).baseline()
    offline = llm_world(scripted, None, DecisionCache(tmp_path))
    found = cli.single_repair(offline, SUCCESS)
    assert [c.proposal.repair_id for c in found.ranked] == [SUCCESS]
    with pytest.raises(KeyError, match="unknown repair"):
        cli.single_repair(offline, "assign.nothing")


# --- P5-3: extracted-PDF context snippets (opt-in) ---------------------------------------------


def test_extracted_context_snippets_are_labelled_and_never_from_the_books(scripted: World) -> None:
    from cascadeguard.knowledge.retrieval import CONTEXT_LABEL

    assert CONTEXT_LABEL == "context only; not citable"
    seen = 0
    for v in scripted.baseline().views:
        if not v.event_id:
            continue
        data = json.loads(build_messages(v, (), snippets=True)[1]["content"])
        block = data["extracted_context"]
        assert block["label"] == CONTEXT_LABEL
        for snip in block["snippets"]:
            seen += 1
            assert snip["label"] == CONTEXT_LABEL
            name = snip["source_file"].casefold()
            assert "abhivardhan" not in name and "oxford handbook" not in name
        assert "extracted_context" not in json.loads(build_messages(v, ())[1]["content"])
    assert seen  # the check ran on real snippets


def test_extracted_context_changes_the_prompt_version_and_label(
    scripted: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plain = LLMAgent("r", MODEL, None, DecisionCache(tmp_path), ())
    extra = LLMAgent("r", MODEL, None, DecisionCache(tmp_path), (), extracted_context=True)
    assert plain.prompt_version != extra.prompt_version
    monkeypatch.setenv("CASCADEGUARD_MODEL", MODEL)
    argv = ["run", SCENARIO, "--agents", "llm", "--offline", "--extracted-context"]
    assert main([*argv, "--cache", str(tmp_path)]) == 0
    assert "extracted-PDF context snippets (context only; not citable)" in capsys.readouterr().out


# --- Prompt v3: citations grouped by action (human decision 2026-10-25) -----------------------


def test_clause_groups_agree_with_the_engine_scope_rule(scripted: World) -> None:
    """A clause is listed under an action exactly when the engine accepts citing it with that
    action proposed (both directions)."""
    from cascadeguard.engine.constraints import ANALYSIS, RuleBook
    from cascadeguard.knowledge.retrieval import ANY_ACTION

    book = RuleBook(scripted.clauses)
    for v in scripted.baseline().views:
        for c in v.role_clauses:
            assert c.citable and c.cite_with
            if c.cite_with == (ANY_ACTION,):
                assert book.concerns(c.id, v.role_id, ())
                continue
            assert not book.concerns(c.id, v.role_id, ())
            for action in v.allowed_actions:
                assert book.concerns(c.id, v.role_id, (action,)) == (action in c.cite_with)
            if ANALYSIS in v.allowed_actions:
                assert ANALYSIS in c.cite_with


def test_prompt_states_the_citation_rules_and_groups(scripted: World) -> None:
    from cascadeguard.knowledge.retrieval import clauses_by_action

    adviser = next(v for v in scripted.baseline().views if v.role_id == "policy_legal_adviser")
    system, user = (m["content"] for m in build_messages(adviser, ()))
    assert "Every citation must support an action you propose in this same decision" in system
    assert "require proposing\n  provide_policy_analysis in this same decision" in system
    data = json.loads(user)
    assert data["citable_clauses_by_action"] == clauses_by_action(adviser.role_clauses)
    assert "role_clauses" not in data
    assert PROMPT_VERSION == "phase5-v3"


# --- Request error detail in the no_decision finding (human decision 2026-10-25) --------------


class FakeStatusError(Exception):
    status_code = 429


def test_request_failure_finding_records_class_status_and_short_message(
    scripted: World, tmp_path: Path
) -> None:
    secret = "sk-or-v1-THISISNOTAREALKEY123456"
    message = f"Rate limit for {MODEL}\nAuthorization: Bearer {secret} retry later"
    base = scripted_replies(scripted)

    def reply(request: dict[str, Any]) -> str | Exception:
        v = view_of(request)
        if (v["role_id"], v["minute"]) == ("telecom_operator", 0):
            return FakeStatusError(message)
        return base(request)

    role_ids = tuple(r.id for r in scripted.roles.roles)
    cache = DecisionCache(tmp_path)
    client = FakeClient(reply)
    agents = {r: LLMAgent(r, MODEL, client, cache, role_ids, redact=(secret,)) for r in role_ids}
    result = replace(scripted, agents=dict(agents), cache=cache).baseline()
    (finding,) = [f for f in result.findings if f.kind == Reason.NO_DECISION.value]
    assert finding.detail.startswith(
        "telecom_operator made no decision at this step (request_failed: request error "
        "FakeStatusError (HTTP 429): Rate limit for <redacted>"
    )
    assert secret not in finding.detail and MODEL not in finding.detail
    assert "\n" not in finding.detail and "Bearer" not in finding.detail
    assert len(finding.detail) < 300


def test_error_detail_only_on_request_failures(scripted: World) -> None:
    view = scripted.baseline().views[0]
    with pytest.raises(ValueError, match="error detail"):
        AgentDecision(
            role_id=view.role_id,
            at=view.at,
            proposed_actions=(),
            rationale="",
            citations=(),
            uncertainty=(),
            no_decision="invalid_output",
            no_decision_detail="X (HTTP 1): y",
        )


def test_error_detail_never_records_headers() -> None:
    """OpenRouter puts response headers into the error body's metadata (seen live, 2026-10-25):
    only the body's message is kept."""
    from cascadeguard.agents.llm import error_detail

    class StatusError(Exception):
        status_code = 429
        body: ClassVar[dict[str, Any]] = {
            "message": "Rate limit exceeded: free-models-per-min.",
            "code": 429,
            "metadata": {"headers": {"X-RateLimit-Limit": "20", "X-RateLimit-Reset": "1"}},
        }

    detail = error_detail(StatusError("Error code: 429 - {... 'headers': {...}}"), ())
    assert detail == "StatusError (HTTP 429): Rate limit exceeded: free-models-per-min."
    plain = error_detail(ConnectionError("reset by peer; headers: {'X-Secret': 'v'}"), ())
    assert plain == "ConnectionError (HTTP None): reset by peer;"
    assert "X-" not in detail + plain


def test_known_limitation_gap_pattern_flags_own_inaction(scripted: World) -> None:
    """KNOWN LIMITATION (PROGRESS.md, human decision 2026-10-25): the free-text gap pattern
    matches "no authority" even when an agent describes its own inaction (seen in the v2 LLM
    baseline, health_data_oversight T+00). The decision is rejected as uncited_gap_claim. This
    test pins the current behaviour; a later fix must change it on purpose."""
    from cascadeguard.engine.constraints import GAP_CLAIM, ConstraintEngine
    from cascadeguard.simulation.state import SimulationState

    text = (
        "No facts are currently known to me, and no authority has been triggered that would "
        "justify issuing a determination at this time."
    )
    assert [m.group(0) for m in GAP_CLAIM.finditer(text)] == ["no authority"]
    state = SimulationState(scripted.scenario, scripted.roles)
    engine = ConstraintEngine(state, scripted.clauses, scripted.corpus_ids)
    engine.release(scripted.scenario.events[0])
    role = "health_data_oversight"
    engine.process(
        AgentDecision(
            role_id=role,
            at=scripted.scenario.time_at(0),
            proposed_actions=(ProposedAction(action_type="monitor"),),
            rationale=text,
            citations=(),
            uncertainty=(),
        ),
        expected_role=role,
    )
    assert [f.kind for f in state.findings if f.role == role] == [Reason.UNCITED_GAP_CLAIM.value]


# --- Inconclusive verdict when steps fail for infrastructure reasons (2026-10-25) --------------


def test_failed_steps_make_the_comparison_inconclusive_everywhere(
    scripted: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from cascadeguard import cli
    from cascadeguard.cli import format_result
    from cascadeguard.storage.export import comparison_export, comparison_markdown, run_export

    base = scripted_replies(scripted)
    fill = FakeClient(base)
    llm_world(scripted, fill, DecisionCache(tmp_path)).baseline()  # cached baseline

    def reply(request: dict[str, Any]) -> str | Exception:
        v = view_of(request)
        if v["role_id"] == "telecom_operator" and v["minute"] in (15, 30):
            return ConnectionError("down")
        return base(request)

    w = llm_world(scripted, FakeClient(reply), DecisionCache(tmp_path))
    c = cli.single_repair(w, SUCCESS).comparison(SUCCESS)
    expected = "inconclusive: 2 steps failed for infrastructure reasons"
    assert c.outcome == expected
    assert c.failed_steps == (
        ("replay", 15, "telecom_operator", "request_failed"),
        ("replay", 30, "telecom_operator", "request_failed"),
    )
    data = comparison_export(c)
    assert data["outcome"] == expected and len(data["failed_steps"]) == 2
    markdown = comparison_markdown(c)
    assert f"**{expected}**" in markdown and "replay T+15 telecom_operator" in markdown
    # CLI: the same verdict.
    w2 = llm_world(scripted, FakeClient(reply), DecisionCache(tmp_path))
    _patch_world(monkeypatch, w2)
    assert main(["run", SCENARIO, "--repair", SUCCESS, "--agents", "llm", "--live"]) == 0
    assert expected in capsys.readouterr().out
    # A baseline with a failed step says so in the text and the JSON export.
    failing = llm_world(
        scripted, FakeClient(lambda _: ConnectionError("x")), DecisionCache(tmp_path / "b")
    )
    result = failing.baseline()
    assert len(result.failed_steps) == 36
    assert run_export(result)["failed_steps"][0]["reason"] == "request_failed"
    assert "INCOMPLETE RUN: 36 steps had no decision" in format_result(result)


def test_complete_runs_keep_their_verdict(scripted: World) -> None:
    c = search_repairs(SCENARIO).comparison(SUCCESS)
    assert c.outcome == "resolved" and not c.failed_steps
    assert "failed_steps" not in c.summary()
