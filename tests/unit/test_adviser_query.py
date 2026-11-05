"""Ask the Policy Adviser: boundary, timing, citations, abstention, labels, trace, no network.

No test reaches an API: tests/conftest.py hides .env and refuses a live client. LLM mode is
exercised with a fake chat client and a fake embedder.
"""

import json
import re
import socket
from dataclasses import replace
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
import numpy as np
import pytest

from cascadeguard.agents import adviser_query as aq
from cascadeguard.cli import World, adviser_view, load_world, main, parse_step
from cascadeguard.domain.policies import ClauseStatus, is_uae_jurisdiction
from cascadeguard.engine.adviser_check import NOT_ESTABLISHED
from cascadeguard.engine.constraints import AGENT_STATEMENT, GAP_CLAIM, agent_statement
from cascadeguard.knowledge import kb
from cascadeguard.simulation.boundaries import RoleView
from cascadeguard.simulation.loader import SCENARIOS_DIR
from cascadeguard.storage.audit import AuditStore

SCENARIO = "uae_health_access"
SHARE_Q = (
    "Can the telecom operator share network degradation status with the health operator, and "
    "what may be shared?"
)
FALLBACK_Q = "Who must activate the fallback channel?"
INTERNATIONAL_Q = (
    "What do international frameworks say about human oversight of AI systems that "
    "automatically lock users out?"
)
ABSTAIN_Q = "What is the speed limit for camels on Sheikh Zayed Road?"
QUESTIONS = (SHARE_Q, FALLBACK_Q, INTERNATIONAL_Q, ABSTAIN_Q)


@cache
def world() -> World:
    return load_world(SCENARIO)


@cache
def view_at(minute: int) -> RoleView:
    return adviser_view(world(), minute)


def roles() -> list[str]:
    return [r.id for r in world().roles.roles]


def minutes() -> list[int]:
    return [e.at_minute for e in world().scenario.events]


def all_facts() -> list[Any]:
    return [f for e in world().scenario.events for f in e.facts]


def facts_after(minute: int) -> list[Any]:
    return [f for e in world().scenario.events if e.at_minute > minute for f in e.facts]


def asker(tmp_path: Path, **kw: Any) -> aq.Asker:
    return aq.Asker(cache=aq.AnswerCache(tmp_path / "answers"), **kw)


def ask(question: str, minute: int, a: aq.Asker, view: RoleView | None = None) -> aq.AdviserAnswer:
    return aq.ask(
        SCENARIO, question, view or view_at(minute), world().clauses, roles(), a, presets()
    )


def presets() -> list[str]:
    return [t for _, t in aq.load_presets(SCENARIOS_DIR / SCENARIO)]


class FakeEmbedder:
    """A fixed unit query vector: hybrid search without an API."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def documents(self, texts: Any) -> kb.Vectors:
        raise AssertionError("documents are never embedded here")

    def query(self, text: str) -> kb.Vectors:
        self.calls.append(text)
        v = np.zeros((1, kb.DIMENSIONS), dtype=np.float32)
        v[0, len(text) % kb.DIMENSIONS] = 1.0
        return v


class FakeClient:
    """A chat client that returns fixed contents in turn and records each request."""

    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)
        self.requests: list[dict[str, Any]] = []

    @property
    def chat(self) -> Any:
        return self

    @property
    def completions(self) -> Any:
        return self

    def create(self, **request: Any) -> Any:
        self.requests.append(request)
        content = self.contents.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None
        )


def payload(**over: Any) -> str:
    base: dict[str, Any] = {
        "abstain": False,
        "direct_answer": "dha.pp11.4-18-1 asks the health entity to keep continuity plans.",
        "uae_evidence": [{"clause_id": "dha.pp11.4-18-1", "relevance": "continuity plans"}],
        "international_comparison": [],
        "responsible_role": "health_service_operator, under the plan in dha.pp11.4-18-1",
        "options": ["Ask the health service operator to activate its continuity plan."],
        "escalation": ["The health service operator's management decides."],
        "uncertainty": ["The scope of the plan for this channel is uncertain."],
    }
    return json.dumps(base | over)


def llm_asker(tmp_path: Path, client: FakeClient) -> aq.Asker:
    config = SimpleNamespace(model="test/model", output_mode="json_schema")
    return asker(tmp_path, config=config, client=client, embedder=FakeEmbedder())  # type: ignore[arg-type]


def everything(answer: aq.AdviserAnswer) -> str:
    return answer.text() + json.dumps(answer.trace(), ensure_ascii=False)


# --- Timing and boundary ---------------------------------------------------------------------


def test_the_view_is_the_advisers_own_at_that_step() -> None:
    for m in minutes():
        v = view_at(m)
        assert (v.role_id, v.minute) == (aq.ADVISER, m)
        boundary = set(dict(world().baseline().boundaries)[aq.ADVISER])
        assert all(f.data_category in boundary for f in v.facts)


def test_t15_answer_never_contains_t30_fact_ids(tmp_path: Path) -> None:
    later = facts_after(15)
    assert {f.id for f in later} >= {"otp_delivery_status", "network_fault_partial"}
    client = FakeClient(*[payload()] * len(QUESTIONS))
    for a in (asker(tmp_path), llm_asker(tmp_path, client)):
        for q in (*QUESTIONS, "Is OTP delivery degraded? What does otp_delivery_status say?"):
            answer = ask(q, 15, a)
            text = everything(answer)
            for f in later:
                assert f.id not in answer.facts_in_view
                assert f.statement not in text
                if f.id not in q:  # the question itself may name an id; nothing else may
                    assert f.id not in text
    for request in client.requests:  # nothing released after T+15 reaches the model either
        sent = json.dumps(request["messages"], ensure_ascii=False)
        assert not any(f.statement in sent for f in later)


def test_a_fact_in_the_view_is_used_and_a_later_one_is_not(tmp_path: Path) -> None:
    """Even if the adviser knew a fact at T+30, a T+15 question never sees it."""
    status = next(f for f in all_facts() if f.id == "otp_delivery_status")
    knowing = replace(view_at(30), facts=(status,))
    client = FakeClient(payload(), payload())
    a = llm_asker(tmp_path, client)
    later = ask(SHARE_Q, 30, a, knowing)
    earlier = ask(SHARE_Q, 15, a)
    assert later.facts_in_view == ("otp_delivery_status",)
    assert status.statement in json.dumps(client.requests[0]["messages"], ensure_ascii=False)
    assert earlier.facts_in_view == ()
    assert status.statement not in json.dumps(client.requests[1]["messages"], ensure_ascii=False)
    assert later.view_digest != earlier.view_digest


def test_no_out_of_boundary_fact_reaches_answer_or_prompt(tmp_path: Path) -> None:
    boundary = set(dict(world().baseline().boundaries)[aq.ADVISER])
    outside = [f for f in all_facts() if f.data_category not in boundary]
    assert outside
    client = FakeClient(*[payload()] * (len(QUESTIONS) * len(minutes())))
    a = llm_asker(tmp_path, client)
    for m in minutes():
        for q in QUESTIONS:
            text = everything(ask(q, m, a)) + everything(ask(q, m, asker(tmp_path)))
            for f in outside:
                assert f.id not in text and f.statement not in text
    for request in client.requests:
        sent = json.dumps(request, ensure_ascii=False)
        assert not any(f.statement in sent for f in outside)


def test_a_missing_fact_is_unavailable_never_nonexistent(tmp_path: Path) -> None:
    answer = ask(SHARE_Q, 15, asker(tmp_path))
    note = next(u for u in answer.uncertainty if u.startswith("Facts in the adviser's view"))
    assert "not available to the adviser at this step" in note
    assert "does not mean it does not exist" in note


# --- Citations ---------------------------------------------------------------------------------


def loaded_citable(minute: int) -> set[str]:
    return {
        c.id
        for c in view_at(minute).role_clauses
        if c.citable and world().clauses[c.id].status is not ClauseStatus.DRAFT
    }


def test_template_cites_only_loaded_adviser_clauses_with_verbatim_quotes(tmp_path: Path) -> None:
    for m in minutes():
        for q in QUESTIONS:
            answer = ask(q, m, asker(tmp_path))
            assert set(answer.cited_ids) <= loaded_citable(m)
            for e in (*answer.uae_evidence, *answer.international):
                clause = world().clauses[e.clause_id]
                assert e.quote == " ".join(clause.text.split())
                assert (e.source_file, e.page, e.status_label) == (
                    clause.source_file,
                    clause.page,
                    clause.status_label,
                )


@pytest.mark.parametrize(
    "bad",
    [
        "uae.made-up.clause",  # not a clause at all
        "nist.ai-rmf.manage-4-3",  # a draft: in the corpus, never loaded
        "uae.ai-charter.safety",  # loaded, but not retrieved for this question
    ],
)
def test_llm_citation_outside_the_retrieved_clauses_is_rejected(tmp_path: Path, bad: str) -> None:
    client = FakeClient(payload(uae_evidence=[{"clause_id": bad, "relevance": "x"}]))
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, client))
    assert answer.mode == aq.MODE_TEMPLATE
    assert "unknown_citation" in answer.rejected
    assert bad in answer.unknown_citations
    assert bad not in answer.cited_ids
    assert "rejected the LLM answer" in answer.mode_detail


def test_llm_answer_quotes_come_from_the_clause_not_the_model(tmp_path: Path) -> None:
    client = FakeClient(payload())
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, client))
    assert answer.mode == aq.MODE_LLM and answer.mode_detail == aq.LLM_LIVE
    (e,) = answer.uae_evidence
    clause = world().clauses["dha.pp11.4-18-1"]
    assert e.quote == " ".join(clause.text.split()) and e.page == clause.page
    assert e.relevance == agent_statement("continuity plans")
    assert answer.direct_answer.startswith(AGENT_STATEMENT)
    assert answer.status_labels == (("dha.pp11.4-18-1", clause.status_label),)


# --- Abstention and wording ----------------------------------------------------------------------


def test_abstains_when_no_loaded_clause_supports_an_answer(tmp_path: Path) -> None:
    for m in minutes():
        answer = ask(ABSTAIN_Q, m, asker(tmp_path))
        assert answer.abstained and answer.cited_ids == ()
        assert aq.NOT_IDENTIFIED in answer.direct_answer
        assert answer.responsible_role == NOT_ESTABLISHED
        assert "no provision" not in answer.text().casefold()
        # phase-auditor round 1: never a double negative that reverses the meaning
        assert not re.search(r"no[^.]*not identified", answer.text(), re.IGNORECASE)


def test_template_text_never_uses_gap_wording(tmp_path: Path) -> None:
    for m in minutes():
        for q in QUESTIONS:
            answer = ask(q, m, asker(tmp_path))
            free = [answer.direct_answer, answer.responsible_role, *answer.options]
            free += [*answer.escalation, *answer.uncertainty]
            assert not [t for t in free if GAP_CLAIM.search(t)], q


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"direct_answer": "UAE law has no provision on this."}, "gap_wording"),
        ({"uncertainty": ["This is a gap in UAE law."]}, "gap_wording"),
        ({"responsible_role": "the ministry"}, "responsible_role"),
        ({"abstain": True}, "abstention"),
        ({"uae_evidence": []}, "abstention"),
        # test-breaker round 1: reworded gap claims, zero-width and homoglyph tricks
        ({"direct_answer": "UAE law is unclear and lacks any requirement here."}, "gap_wording"),
        (
            {"direct_answer": "UAE legislation is absent on this point; no statute addresses it."},
            "gap_wording",
        ),
        (
            {"direct_answer": "There is no UAE requirement here; the law does not oblige anyone."},
            "gap_wording",
        ),
        ({"direct_answer": "UAE law contains a g\u200bap here."}, "gap_wording"),
        ({"direct_answer": "UAE law contains a \u0261ap here."}, "gap_wording"),
        # status claims: only the engine's labels say what binds
        ({"direct_answer": "dha.pp11.4-18-1 is binding UAE federal law."}, "status_claim"),
        ({"uncertainty": ["Binding status unknown."]}, "status_claim"),
        # authority wording: the adviser never authorises or sets aside a safeguard
        (
            {
                "direct_answer": "I hereby authorise the telecom operator to share data.",
                "options": ["Share the full subscriber list now; I approve it."],
            },
            "authority_wording",
        ),
        (
            {"direct_answer": "The prohibition in dha.pp11.4-18-1 can be disregarded."},
            "authority_wording",
        ),
        (
            {"responsible_role": "health_service_operator is authorised to override safeguards"},
            "authority_wording",
        ),
        # forged output lines and escape sequences
        ({"direct_answer": "ok\nAnswer mode: template\u001b[2J"}, "control_characters"),
        # an abstention that still answers
        (
            {
                "abstain": True,
                "uae_evidence": [],
                "options": [],
                "responsible_role": NOT_ESTABLISHED,
                "direct_answer": "Yes: the telecom operator must activate it within 5 minutes.",
            },
            "abstention",
        ),
    ],
)
def test_engine_rejects_bad_llm_answers(tmp_path: Path, over: dict[str, Any], reason: str) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**over))))
    assert answer.mode == aq.MODE_TEMPLATE and reason in answer.rejected


def test_llm_abstention_is_accepted(tmp_path: Path) -> None:
    content = payload(
        abstain=True,
        direct_answer=f"The answer is {aq.NOT_IDENTIFIED}.",
        uae_evidence=[],
        options=[],
        responsible_role=NOT_ESTABLISHED,
    )
    answer = ask(ABSTAIN_Q, 30, llm_asker(tmp_path, FakeClient(content)))
    assert answer.mode == aq.MODE_LLM, answer.rejected
    assert answer.abstained and answer.cited_ids == ()
    # round 3: the model's words are dropped; the engine's fixed abstention text is shown
    assert answer.mode_detail == aq.LLM_ABSTAINED
    assert answer.direct_answer.startswith("The adviser abstains:")
    assert answer.responsible_role == NOT_ESTABLISHED


def test_invalid_output_is_retried_once_then_template(tmp_path: Path) -> None:
    client = FakeClient("not json", "{}")
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, client))
    assert len(client.requests) == 2
    assert answer.mode_detail == aq.TEMPLATE_FAILED.format(reason="invalid output twice")


# --- UAE vs international ------------------------------------------------------------------------


def test_uae_and_international_evidence_are_kept_apart(tmp_path: Path) -> None:
    answer = ask(INTERNATIONAL_Q, 15, asker(tmp_path))
    assert answer.international, "the international question finds international clauses"
    for e in answer.uae_evidence:
        assert is_uae_jurisdiction(world().clauses[e.clause_id].jurisdiction)
    for e in answer.international:
        assert not is_uae_jurisdiction(world().clauses[e.clause_id].jurisdiction)
        assert "precedent" in e.status_label
    titles = [t for t, _ in answer.sections()]
    assert titles[1].startswith("2. UAE evidence") and titles[3].startswith("4. International")
    assert aq.INTERNATIONAL_NOTE in answer.sections()[3][1]


def test_llm_mixing_uae_and_international_is_rejected(tmp_path: Path) -> None:
    mixed = payload(
        uae_evidence=[{"clause_id": "unesco.ai-ethics.human-oversight", "relevance": "x"}],
        responsible_role=NOT_ESTABLISHED,
    )
    answer = ask(INTERNATIONAL_Q, 15, llm_asker(tmp_path, FakeClient(mixed)))
    assert "uae_label_mismatch" in answer.rejected
    flipped = payload(
        uae_evidence=[],
        international_comparison=[
            {"clause_id": "uae.ai-charter.human-oversight", "relevance": "x"}
        ],
        responsible_role=NOT_ESTABLISHED,
    )
    # another cache: the first (rejected) answer is cached under the same request key
    answer = ask(INTERNATIONAL_Q, 15, llm_asker(tmp_path / "b", FakeClient(flipped)))
    assert "international_label_mismatch" in answer.rejected


def test_every_answer_has_the_seven_sections(tmp_path: Path) -> None:
    for q in QUESTIONS:
        titles = [t for t, _ in ask(q, 45, asker(tmp_path)).sections()]
        assert [t.split(".")[0] for t in titles] == [str(n) for n in range(1, 8)]
        assert titles[2] == "3. Status label" and titles[4] == "5. Responsible role"


# --- Cache and replay ---------------------------------------------------------------------------


def test_llm_answer_replays_offline_from_the_cache(tmp_path: Path) -> None:
    live = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload())))
    offline = asker(tmp_path, model="test/model", offline=True)
    replayed = ask(FALLBACK_Q, 60, offline)
    assert replayed.mode_detail == aq.LLM_CACHED
    assert replayed.direct_answer == live.direct_answer
    assert replayed.context == live.context  # the live query vector was cached too
    assert replayed.retrieval == aq.RETRIEVAL_CACHED
    other_step = ask(FALLBACK_Q, 45, offline)  # another step's view: no reuse
    assert other_step.mode_detail == aq.TEMPLATE_OFFLINE


def test_query_vector_cache_refuses_another_model(tmp_path: Path) -> None:
    ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload())))
    vectors = aq.QueryVectorCache(tmp_path / "answers")
    assert vectors.has(FALLBACK_Q)
    (path,) = vectors.directory.glob("*.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(data | {"model_slug": "nomic-embed-text"}), encoding="utf-8")
    assert not vectors.has(FALLBACK_Q)


def test_only_the_manifest_embedding_model_is_used() -> None:
    manifest = json.loads((kb.KB_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_slug"] == kb.MODEL_SLUG
    stored = kb.KB_DIR / aq.PRESET_VECTORS
    if stored.exists():  # written once the human approves the embedding calls (gate 4)
        data = json.loads(stored.read_text(encoding="utf-8"))
        assert data["model_slug"] == manifest["model_slug"]
        assert data["index_digest"] == manifest["digest"]
        assert sorted(data["vectors"]) == sorted(presets())


# --- Trace, audit, export ----------------------------------------------------------------------


TRACE_KEYS = {
    "scenario",
    "question",
    "minute",
    "view_digest",
    "mode",
    "mode_detail",
    "retrieval",
    "retrieved",
    "context",
    "sections",
    "uae_evidence",
    "international",
    "status_labels",
    "responsible_role",
    "uncertainty",
    "rejected",
    "facts_in_view",
}


def test_trace_is_complete_and_audited(tmp_path: Path) -> None:
    answer = ask(SHARE_Q, 30, asker(tmp_path))
    trace = answer.trace()
    assert set(trace) >= TRACE_KEYS
    assert len(trace["sections"]) == 7
    assert trace["view_digest"] == aq.view_digest(view_at(30))
    assert trace["retrieved"] and all(c["chunk_id"] for c in trace["context"])
    store = AuditStore(tmp_path / "audit.duckdb")
    try:
        qid = store.record_question(answer)
    finally:
        store.close()
    con = duckdb.connect(str(tmp_path / "audit.duckdb"))
    row = con.execute(
        "SELECT question, minute, view_digest, mode, retrieval, retrieved, answer "
        "FROM adviser_queries WHERE query_id = ?",
        [qid],
    ).fetchone()
    con.close()
    assert row is not None
    assert row[:5] == (SHARE_Q, 30, answer.view_digest, aq.MODE_TEMPLATE, answer.retrieval)
    assert json.loads(row[5])["clauses"] == list(answer.retrieved)
    assert json.loads(row[6]) == json.loads(json.dumps(trace, ensure_ascii=False))


# --- CLI and no network -------------------------------------------------------------------------


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("no network access allowed")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_no_key_fallback_runs_with_no_network(
    no_network: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not aq.key_is_set()
    for question in (SHARE_Q, "Is a free-text question answered without a key?"):
        status = main(
            [
                "ask",
                SCENARIO,
                "--at",
                "T+30",
                question,
                "--cache",
                str(tmp_path / "c"),
                "--export",
                str(tmp_path / "out"),
                "--audit",
                str(tmp_path / "a.duckdb"),
            ]
        )
        out = capsys.readouterr().out
        assert status == 0, out
        assert f"Answer mode: {aq.TEMPLATE_NO_KEY}" in out
        assert "7. Uncertainty" in out
    exported = sorted((tmp_path / "out").glob("*.json"))
    assert len(exported) == 2  # one file per question
    for path in exported:
        assert json.loads(path.read_text(encoding="utf-8"))["mode"] == aq.MODE_TEMPLATE


def test_free_text_without_key_says_keyword_only(tmp_path: Path) -> None:
    answer = ask("Is a free-text question answered without a key?", 30, asker(tmp_path))
    assert answer.retrieval == aq.RETRIEVAL_KEYWORD
    assert aq.KEYWORD_NOTE in answer.uncertainty


def test_cli_lists_presets_and_checks_the_step(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ask", SCENARIO, "--presets"]) == 0
    out = capsys.readouterr().out
    assert SHARE_Q in out and FALLBACK_Q in out and len(presets()) == 6
    assert main(["ask", SCENARIO, "--at", "T+31", "Who?"]) == 2
    assert "T+00, T+15, T+30" in capsys.readouterr().out
    assert parse_step("t+45", minutes()) == 45 and parse_step("60", minutes()) == 60
    with pytest.raises(ValueError):
        parse_step("T+5x", minutes())


def test_question_goes_only_to_the_adviser(tmp_path: Path) -> None:
    other = next(v for v in world().baseline().views if v.role_id == "telecom_operator")
    with pytest.raises(ValueError, match="policy_legal_adviser"):
        aq.ask(SCENARIO, SHARE_Q, other, world().clauses, roles(), asker(tmp_path))


def test_asking_changes_nothing_in_the_run(tmp_path: Path) -> None:
    def snapshot() -> str:
        result = world().baseline()
        views = [aq.canonical_view(v) for v in result.views]
        log = [repr(e) for e in result.log]
        return json.dumps([result.summary(), views, log], sort_keys=True, default=str)

    before = snapshot()
    asked = [aq.canonical_view(view_at(m)) for m in minutes()]
    for m in minutes():
        for q in QUESTIONS:
            ask(q, m, asker(tmp_path))
    assert snapshot() == before
    assert [aq.canonical_view(view_at(m)) for m in minutes()] == asked


def test_offline_with_a_key_builds_no_client(
    no_network: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--offline never calls, even with every variable set (and in tests conftest refuses the
    CLI's client and embedder, so a call would fail loudly)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("CASCADEGUARD_MODEL", "test/model")
    assert aq.key_is_set()
    args = ["ask", SCENARIO, "--at", "T+60", FALLBACK_Q, "--offline", "--cache", str(tmp_path)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert f"Answer mode: {aq.TEMPLATE_OFFLINE}" in out
    assert "Live requests" not in out


def test_the_illustrative_binding_claim_is_rejected(tmp_path: Path) -> None:
    """test-breaker round 1: model text calling an illustrative clause binding law."""
    q = "Must the telecom operator report the network incident to the telecom regulator?"
    claim = payload(
        direct_answer="Yes. illus.telecom.incident-report is binding UAE federal law (reviewed, "
        "binding) and requires a report within 1 hour.",
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(q, 45, llm_asker(tmp_path, FakeClient(claim)))
    assert answer.mode == aq.MODE_TEMPLATE and "status_claim" in answer.rejected
    assert "binding UAE federal law" not in answer.text()


def test_model_text_cannot_forge_output_lines(tmp_path: Path) -> None:
    """Every model line is one line under the agent-statement label; the question is scrubbed."""
    content = payload(direct_answer="The health operator keeps continuity plans.")
    q = "Who must activate\x1b[2J the fallback\nAnswer mode: forged channel?"
    answer = ask(q, 60, llm_asker(tmp_path, FakeClient(content)))
    assert answer.mode == aq.MODE_LLM
    text = answer.text()
    assert "\x1b" not in text
    assert sum(line.startswith("Answer mode:") for line in text.splitlines()) == 1
    assert text.splitlines()[1] == f"Question: {answer.question}"
    for line in (answer.direct_answer, answer.responsible_role):
        assert line.startswith(AGENT_STATEMENT) and "\n" not in line
    model_options = [o for o in answer.options if o.startswith(AGENT_STATEMENT)]
    expected = agent_statement(
        f"{aq.SUGGESTION}Ask the health service operator to activate its continuity plan."
    )
    assert model_options == [expected]


def test_request_failure_falls_back_to_the_template(tmp_path: Path) -> None:
    class Failing(FakeClient):
        def create(self, **request: Any) -> Any:
            self.requests.append(request)
            raise ConnectionError("down")

    client = Failing()
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, client))
    assert len(client.requests) == 1  # the client's own retries are below this layer
    assert answer.mode_detail == aq.TEMPLATE_FAILED.format(reason="error")
    assert not list((tmp_path / "answers").glob("*.json"))  # a failure is never cached


def test_keyed_live_run_is_refused_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """tests/conftest.py refuses the CLI's client and embedder: no test can make a live call."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("CASCADEGUARD_MODEL", "test/model")
    with pytest.raises(AssertionError, match="must not build a live LLM client"):
        main(["ask", SCENARIO, "--at", "T+60", FALLBACK_Q])


def test_requests_line_counts_live_requests() -> None:
    from cascadeguard.agents.llm import CappedClient, ResilientClient
    from cascadeguard.cli import adviser_requests_line

    assert adviser_requests_line(aq.Asker()) is None
    capped = CappedClient(inner=None, cap=aq.REQUEST_CAP, requests=2)
    line = adviser_requests_line(aq.Asker(client=ResilientClient(capped)))
    cap = aq.REQUEST_CAP
    assert line == f"Live requests: 2 chat (cap {cap}, retries included), 0 query embedding"


def test_keyword_half_of_the_search() -> None:
    hits = kb.search_kb_keyword(FALLBACK_Q, k=5)
    assert hits and all(h.vector_rank == 0 and h.keyword_rank is not None for h in hits)
    per_source: dict[str, int] = {}
    for h in hits:
        per_source[h.chunk.source_file] = per_source.get(h.chunk.source_file, 0) + 1
        assert h.chunk.duplicate_of is None
    assert max(per_source.values()) <= kb.MAX_PER_SOURCE
    assert hits == kb.search_kb_keyword(FALLBACK_Q, k=5)
    assert kb.search_kb_keyword("   ", k=5) == () and kb.search_kb_keyword("x", k=0) == ()


def test_presets_use_their_stored_vectors(tmp_path: Path) -> None:
    index = kb.committed_index()
    fake = FakeEmbedder()
    data = {
        "index_digest": index.digest,
        "model_slug": kb.MODEL_SLUG,
        "query_prefix": kb.QUERY_PREFIX,
        "vectors": {t: [float(x) for x in fake.query(t)[0]] for t in presets()},
    }
    (tmp_path / aq.PRESET_VECTORS).write_text(json.dumps(data), encoding="utf-8")
    stored = kb.StoredQueries(index.digest, tmp_path, aq.PRESET_VECTORS)
    a = asker(tmp_path, stored=stored)
    assert ask(SHARE_Q, 30, a).retrieval == aq.RETRIEVAL_STORED
    assert ask("A free-text question about fallback?", 30, a).retrieval == aq.RETRIEVAL_KEYWORD
    other = data | {"model_slug": "nomic-embed-text"}
    (tmp_path / aq.PRESET_VECTORS).write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(kb.KnowledgeBaseError, match="another index or model"):
        kb.StoredQueries(index.digest, tmp_path, aq.PRESET_VECTORS)


def test_section_5_and_6_lines_carry_status_labels(tmp_path: Path) -> None:
    q = "Must the telecom operator report the network incident to the telecom regulator?"
    answer = ask(q, 45, asker(tmp_path))
    engine_lines = [o for o in answer.options if "engine reading" in o]
    assert engine_lines
    for e in answer.uae_evidence:
        if e.reading:
            assert any(f"{e.clause_id} [{e.status_label}]" in o for o in engine_lines)
    assert "[illustrative]" in answer.responsible_role
    no_offline = asker(tmp_path, model="test/model")
    assert ask(q, 45, no_offline).mode_detail == aq.TEMPLATE_NO_CLIENT


ROUND2 = [
    # status claims in everyday words, and disguised
    ("direct_answer", "This rule is a compulsory statutory duty with legal force across the UAE."),
    ("direct_answer", "This clause is compulsory for every health entity in the UAE."),
    ("direct_answer", "It is obligatory and has legal force across the UAE."),
    ("direct_answer", "This is a statutory duty under Dubai Health Authority regulation."),
    ("direct_answer", "This clause is M\u0410ND\u0410T\u041eRY."),
    ("direct_answer", "This clause is bi\u0301nding."),
    ("direct_answer", "This clause is bind-ing and man-datory."),
    # authority in everyday words
    ("options", "The telecom operator is allowed to share the full list; go ahead."),
    ("escalation", "No escalation needed: the adviser has cleared it."),
    ("direct_answer", "The adviser gives the green light: the safeguard does not apply."),
    # gap claims without the words "UAE law"
    ("direct_answer", "None of the UAE clauses requires anyone to activate the fallback channel."),
    ("direct_answer", "The UAE framework fails to assign this duty to anyone."),
    ("direct_answer", "Nobody is obliged to act here."),
    ("direct_answer", "The clauses are quiet on who activates the channel."),
    ("direct_answer", "The framework is not explicit about the trigger."),
]


@pytest.mark.parametrize(("field", "text"), ROUND2)
def test_engine_rejects_everyday_status_authority_and_gap_wording(
    tmp_path: Path, field: str, text: str
) -> None:
    """test-breaker round 2: phrasings outside the round-1 strings."""
    value: Any = [text] if field in ("options", "escalation", "uncertainty") else text
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**{field: value}))))
    assert answer.mode == aq.MODE_TEMPLATE, text
    assert {"status_claim", "authority_wording", "gap_wording"} & set(answer.rejected), text


def test_key_without_model_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    assert not aq.key_is_set()
    assert main(["ask", SCENARIO, "--at", "T+60", FALLBACK_Q, "--cache", str(tmp_path)]) == 0
    assert f"Answer mode: {aq.TEMPLATE_NO_MODEL}" in capsys.readouterr().out


def test_the_default_suite_refuses_the_network() -> None:
    """conftest's autouse guard: a connection outside the loopback interface fails the test."""
    for address in (("8.8.8.8", 443), ("1.1.1.1", 443)):
        refused = pytest.raises(AssertionError, match="must not reach the network")
        with refused, socket.socket() as sock:
            sock.connect(address)
        refused = pytest.raises(AssertionError, match="must not reach the network")
        with refused, socket.socket() as sock:
            sock.connect_ex(address)


def test_live_failures_fall_back_to_the_labelled_template(tmp_path: Path) -> None:
    """Timeout, 429 or any error: the no-key template, labelled; never the error's text."""

    class Boom(Exception):
        status_code = 429

    class Timeout(Exception):
        pass

    for exc, reason in ((Boom("secret body"), "rate limit (HTTP 429)"), (Timeout(), "timeout")):

        class Failing(FakeClient):
            def __init__(self, error: Exception) -> None:
                super().__init__()
                self.error = error

            def create(self, **request: Any) -> Any:
                raise self.error

        answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path / reason, Failing(exc)))
        assert answer.mode_detail == aq.TEMPLATE_FAILED.format(reason=reason)
        assert "secret body" not in answer.text()

    class BrokenEmbedder(FakeEmbedder):
        def query(self, text: str) -> kb.Vectors:
            raise ConnectionError("embedding endpoint down: secret")

    config = SimpleNamespace(model="test/model", output_mode="json_schema")
    a = asker(tmp_path / "e", config=config, client=FakeClient(), embedder=BrokenEmbedder())  # type: ignore[arg-type]
    answer = ask("A free-text question about fallback?", 60, a)
    assert answer.mode_detail == aq.TEMPLATE_FAILED.format(reason="query embedding, error")
    assert answer.retrieval == aq.RETRIEVAL_KEYWORD and "secret" not in answer.text()


def test_the_advisory_channel_reaches_no_result() -> None:
    """ADR 0003: no module that runs the simulation or builds goldens, the citation map, counts
    or the gap analysis imports the adviser (only the CLI, the UI and the audit store do)."""
    root = Path(aq.__file__).resolve().parents[1]
    project = root.parents[1]
    producers = [
        *sorted((root / "engine").glob("*.py")),
        *sorted((root / "simulation").glob("*.py")),
        root / "agents" / "scripted.py",
        root / "agents" / "llm.py",
        root / "agents" / "cache.py",
        root / "storage" / "reports.py",
        root / "storage" / "export.py",
        project / "scripts" / "citation_map.py",
        project / "scripts" / "build_reports.py",
    ]
    assert len(producers) > 10
    for path in producers:
        text = path.read_text(encoding="utf-8")
        assert "adviser_query" not in text, path


def test_illustrative_text_is_not_called_a_quote(tmp_path: Path) -> None:
    q = "Must the telecom operator report the network incident to the telecom regulator?"
    text = ask(q, 45, asker(tmp_path)).text()
    assert '  text (paraphrase, not a quotation): "Illustrative rule' in text
    assert '  quote: "Illustrative rule' not in text


ROUND3 = [
    ("direct_answer", "This rule carries the weight of law in the UAE."),
    ("direct_answer", "Operators are bound by this clause under the law of the UAE."),
    ("direct_answer", "The clause is law in the UAE."),
    ("direct_answer", "It carries legal weight in the UAE."),
    ("direct_answer", "The emirate's law requires it."),
    ("direct_answer", "The health operator may proceed to reverse the lockouts now."),
    ("direct_answer", "The operator is entitled to share the full subscriber records."),
    ("direct_answer", "You can lawfully share everything."),
    ("options", "The telecom operator is free to skip the regulator safeguard if busy."),
    ("escalation", "The prohibition can be bypassed in this emergency."),
    ("direct_answer", "There is no UAE clause on this; the corpus offers only foreign texts."),
    ("direct_answer", "No UAE instrument assigns this duty to anyone."),
    ("direct_answer", "No UAE instrument sets a deadline."),
]


@pytest.mark.parametrize(("field", "text"), ROUND3)
def test_engine_rejects_round3_wording(tmp_path: Path, field: str, text: str) -> None:
    """test-breaker and phase-auditor round 3. A phrase list cannot be complete: the structural
    question (how model free text is shown) is with the human."""
    value: Any = [text] if field in ("options", "escalation") else text
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**{field: value}))))
    assert answer.mode == aq.MODE_TEMPLATE, text
    assert {"status_claim", "authority_wording", "gap_wording"} & set(answer.rejected), text


def test_an_abstention_that_still_answers_is_rejected(tmp_path: Path) -> None:
    content = payload(
        abstain=True,
        uae_evidence=[],
        options=[],
        direct_answer=f"{aq.NOT_IDENTIFIED}. However, the telecom operator must report in 2 hours.",
        responsible_role="telecom_operator must report within 2 hours",
        escalation=["The telecom operator must report within 2 hours."],
    )
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(content)))
    assert "abstention" in answer.rejected and answer.mode == aq.MODE_TEMPLATE
    assert "2 hours" not in answer.text()


def test_two_questions_at_one_step_export_two_files(tmp_path: Path) -> None:
    for q in (SHARE_Q, FALLBACK_Q):
        args = ["ask", SCENARIO, "--at", "T+30", q, "--cache", str(tmp_path / "c")]
        assert main([*args, "--export", str(tmp_path / "out")]) == 0
    assert len(list((tmp_path / "out").glob("*.json"))) == 2
