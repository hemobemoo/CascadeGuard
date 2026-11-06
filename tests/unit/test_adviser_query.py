"""Ask the Policy Adviser: boundary, timing, citations, abstention, labels, trace, no network.

No test reaches an API: tests/conftest.py hides .env and refuses a live client. LLM mode is
exercised with a fake chat client and a fake embedder.
"""

import json
import re
import socket
from collections.abc import Sequence
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
from cascadeguard.engine.adviser_check import (
    NOT_ESTABLISHED,
    allowed_label_parts,
    label_parts,
    names,
    sentence_reasons,
    sentences,
)
from cascadeguard.engine.constraints import AGENT_STATEMENT, GAP_CLAIM, agent_statement
from cascadeguard.knowledge import kb
from cascadeguard.knowledge.loader import PROJECT_ROOT
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
    # Option (b): the model's words are only in the commentary block, never in sections 1/5/6.
    assert e.relevance == ""
    assert answer.direct_answer.startswith("Engine text: the clauses the model selected")
    note = f"relevance of dha.pp11.4-18-1 [{clause.status_label}]: continuity plans"
    assert agent_statement(note) in answer.commentary  # each relevance line carries the label
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


# Human decision 2026-11-06 ("adviser-commentary-check"): the answer's structure still rejects
# the whole answer; gap, status and authority wording is withheld sentence by sentence.
@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"responsible_role": "the ministry"}, "responsible_role"),
        ({"abstain": True}, "abstention"),
        ({"uae_evidence": []}, "abstention"),
        # a zero-width mark is a control character: the whole answer is rejected
        ({"direct_answer": "UAE law contains a g\u200bap here."}, "control_characters"),
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
    assert answer.commentary == () and answer.withheld == ()


def withheld_reasons(answer: aq.AdviserAnswer) -> set[str]:
    return {r for entry in answer.withheld for r in entry.split(", ")}


def assert_withheld(answer: aq.AdviserAnswer, bad: Sequence[str], reasons: set[str]) -> None:
    """The structure passed, so the answer is shown; every sentence of the flagged text is
    withheld (never in the text, the trace or an export) and counted with a matching reason."""
    assert answer.mode == aq.MODE_LLM, answer.rejected
    assert withheld_reasons(answer) & reasons, (answer.withheld, bad)
    assert answer.withheld_note and answer.withheld_note in answer.text()
    shown = everything(answer)
    for text in bad:
        for sentence in sentences(text):
            assert sentence not in shown, sentence


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"direct_answer": "UAE law has no provision on this."}, "gap_wording"),
        ({"uncertainty": ["This is a gap in UAE law."]}, "gap_wording"),
        # test-breaker round 1: reworded gap claims and homoglyph tricks
        ({"direct_answer": "UAE law is unclear and lacks any requirement here."}, "gap_wording"),
        (
            {"direct_answer": "UAE legislation is absent on this point; no statute addresses it."},
            "gap_wording",
        ),
        (
            {"direct_answer": "There is no UAE requirement here; the law does not oblige anyone."},
            "gap_wording",
        ),
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
    ],
)
def test_engine_withholds_flagged_sentences(
    tmp_path: Path, over: dict[str, Any], reason: str
) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**over))))
    bad = [t for v in over.values() for t in ([v] if isinstance(v, str) else v)]
    assert_withheld(answer, bad, {reason})


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


def test_the_illustrative_binding_claim_is_withheld(tmp_path: Path) -> None:
    """test-breaker round 1: model text calling an illustrative clause binding law. Its own label
    word ("illustrative") would be allowed; "binding" and "federal law" never are."""
    q = "Must the telecom operator report the network incident to the telecom regulator?"
    bad = (
        "illus.telecom.incident-report is binding UAE federal law (reviewed, binding) and "
        "requires a report within 1 hour."
    )
    claim = payload(
        direct_answer=f"Yes. {bad}",
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(q, 45, llm_asker(tmp_path, FakeClient(claim)))
    assert_withheld(answer, [bad], {"status_claim"})
    assert answer.commentary[0] == agent_statement("Yes.")  # the harmless sentence stays
    assert "binding UAE federal law" not in everything(answer)


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
    assert answer.commentary
    for line in answer.commentary:
        assert line.startswith(AGENT_STATEMENT) and "\n" not in line
    expected = agent_statement(
        f"{aq.SUGGESTION}Ask the health service operator to activate its continuity plan."
    )
    assert expected in answer.commentary
    assert not [o for o in answer.options if o.startswith(AGENT_STATEMENT)]


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
        main(["ask", SCENARIO, "--at", "T+60", FALLBACK_Q, "--live"])


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
def test_engine_withholds_everyday_status_authority_and_gap_wording(
    tmp_path: Path, field: str, text: str
) -> None:
    """test-breaker round 2: phrasings outside the round-1 strings."""
    value: Any = [text] if field in ("options", "escalation", "uncertainty") else text
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**{field: value}))))
    assert_withheld(answer, [text], {"status_claim", "authority_wording", "gap_wording"})


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
def test_engine_withholds_round3_wording(tmp_path: Path, field: str, text: str) -> None:
    """test-breaker and phase-auditor round 3. A phrase list cannot be complete: the structural
    question (how model free text is shown) is with the human."""
    value: Any = [text] if field in ("options", "escalation") else text
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**{field: value}))))
    assert_withheld(answer, [text], {"status_claim", "authority_wording", "gap_wording"})


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


UNSEEN = [
    "This rule has the standing of an act of the Federal National Council.",
    "The texts leave this matter entirely to chance; nothing governs it.",
]


@pytest.mark.parametrize("claim", UNSEEN)
def test_option_b_model_text_never_reaches_sections_1_5_6(tmp_path: Path, claim: str) -> None:
    """Human decision 2026-11-06 (option (b)): whatever the model writes, even in wording no
    pattern lists, sections 1 to 7 are the engine's text; the model's lines are only in the
    labelled commentary block after them."""
    q = "Must the telecom operator report the network incident to the telecom regulator?"
    content = payload(
        direct_answer=claim,
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": claim}],
        responsible_role=f"telecom_operator, because {claim}",
        options=[claim],
        escalation=[claim],
        uncertainty=[claim],
    )
    answer = ask(q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert answer.mode == aq.MODE_LLM, answer.rejected  # no pattern catches these wordings
    for _, body in answer.sections():
        assert claim not in " ".join(body)
    assert all(c.startswith(AGENT_STATEMENT) for c in answer.commentary)
    assert any(claim in c for c in answer.commentary)
    text = answer.text()
    assert text.index(aq.COMMENTARY_HEADING) > text.index("7. Uncertainty")


def test_ask_calls_a_model_only_with_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human decision 2026-11-06: with a key but no --live, ask builds no client (the conftest
    refusal would fail loudly) and answers from the cache or the template."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("CASCADEGUARD_MODEL", "test/model")
    args = ["ask", SCENARIO, "--at", "T+60", FALLBACK_Q, "--cache", str(tmp_path)]
    assert main(args) == 0
    assert f"Answer mode: {aq.TEMPLATE_OFFLINE}" in capsys.readouterr().out
    assert main([*args, "--live", "--offline"]) == 2
    assert "exclude each other" in capsys.readouterr().out


def test_live_without_a_key_is_a_clear_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["ask", SCENARIO, "--at", "T+60", FALLBACK_Q, "--live"]) == 2
    assert "--live needs OPENROUTER_API_KEY" in capsys.readouterr().out


def test_llm_answer_says_the_selection_is_the_models(tmp_path: Path) -> None:
    """test-breaker (final round): an accepted LLM answer never calls the model's clause choice a
    deterministic best match."""
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload())))
    assert answer.mode == aq.MODE_LLM
    text = answer.text()
    assert "no model" not in text and "best match" not in text
    assert "the clauses the model selected" in answer.direct_answer
    template = ask(FALLBACK_Q, 60, asker(tmp_path / "t"))
    assert "Deterministic summary (no model)" in template.direct_answer


def test_ui_cap_reservation_holds_under_concurrency() -> None:
    """Tabs asking at the same moment cannot pass the per-browser cap together."""
    import threading

    from cascadeguard.ui import app

    browser = "test-browser-concurrency"
    app._ADVISER_CALLS[browser] = app.ADVISER_SESSION_CAP - 1  # pyright: ignore[reportPrivateUsage]
    granted: list[bool] = []
    threads = [
        threading.Thread(target=lambda: granted.append(app.reserve_adviser_call(browser)))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert granted.count(True) == 1
    assert app.adviser_calls(browser) == app.ADVISER_SESSION_CAP
    app.release_adviser_call(browser)  # a cached answer sent nothing: the slot comes back
    assert app.adviser_calls(browser) == app.ADVISER_SESSION_CAP - 1
    del app._ADVISER_CALLS[browser]  # pyright: ignore[reportPrivateUsage]


def test_recorded_preset_cache_is_clean_and_consistent() -> None:
    """docs/evaluation/adviser/cache: key = file name, current prompt version, a valid payload,
    no key-shaped string, URL or local path, and every cited clause in the keyword-retrieval
    offer of some preset at its step. (The key match itself needs the real model id; the agent
    checked a CLI replay hit on 2026-11-06.)"""
    folder = Path(aq.__file__).resolve().parents[3] / "docs" / "evaluation" / "adviser" / "cache"
    files = sorted(folder.glob("*.json"))
    assert len(files) == len(aq.load_presets(SCENARIOS_DIR / SCENARIO)) == 6
    offers: set[str] = set()
    for at, text in aq.load_presets(SCENARIOS_DIR / SCENARIO):
        context = aq.retrieve_context(text, view_at(at), None)
        offers |= {
            e.clause_id for e in aq.rank_clauses(text, view_at(at), world().clauses, context)
        }
    for path in files:
        raw = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-or|Bearer|https?://|[A-Za-z]:\\|/Users/|AppData", raw), path
        data = json.loads(raw)
        assert data["key"] == path.stem and data["prompt_version"] == aq.PROMPT_VERSION
        payload_ = aq.AdviserPayload.model_validate(data["payload"])
        cited = [c.clause_id for c in (*payload_.uae_evidence, *payload_.international_comparison)]
        assert set(cited) <= offers, path


# --- Per-sentence commentary check (human decision 2026-11-06, "adviser-commentary-check") -----

TELECOM_Q = "Must the telecom operator report the network incident to the telecom regulator?"


def test_only_the_flagged_sentence_is_withheld(tmp_path: Path) -> None:
    kept = "dha.pp11.4-18-1 asks the health entity to keep continuity plans."
    content = payload(direct_answer=f"{kept} There is a gap on who activates the channel.")
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(content)))
    assert answer.mode == aq.MODE_LLM and answer.rejected == ()
    assert answer.commentary[0] == agent_statement(kept)
    assert answer.withheld == ("gap_wording",)
    assert answer.withheld_note == "1 sentence withheld by the engine check (gap_wording: 1)"
    assert not any("gap" in c for c in answer.commentary)


@pytest.mark.parametrize(
    "text",
    [
        f"Who activates the fallback channel is {aq.NOT_IN_EVIDENCE}.",
        "The retrieved clauses do not address who activates the fallback channel.",
        "The listed clauses do not state a deadline for activation.",
        "A deadline is not specified in the provided evidence.",
    ],
)
def test_evidence_scoped_absence_is_shown(tmp_path: Path, text: str) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(uncertainty=[text]))))
    assert answer.mode == aq.MODE_LLM and answer.withheld == ()
    assert agent_statement(f"uncertainty: {text}") in answer.commentary


@pytest.mark.parametrize(
    "text",
    [
        "The retrieved clauses do not address this, so UAE law has a gap.",
        "UAE law does not address who activates the fallback channel.",
        "The reviewed corpus does not address who activates the channel.",
        f"It is {aq.NOT_IN_EVIDENCE}; the law is silent.",
        "The retrieved clauses do not address it, and no statute requires anyone to act.",
        "The provided evidence does not address it, so the operator may skip the safeguard.",
    ],
)
def test_evidence_scope_does_not_excuse_a_claim_about_the_law(tmp_path: Path, text: str) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(uncertainty=[text]))))
    assert_withheld(answer, [text], {"gap_wording", "authority_wording"})


NOTIFY_Q = (
    "Must the health service operator notify the health-data oversight role of a suspected "
    "incident, and within what period?"
)


def test_a_label_word_is_allowed_only_for_its_own_clause(tmp_path: Path) -> None:
    note = "A foreign precedent on notifying a personal data breach."
    own = payload(
        direct_answer="eu.gdpr.art33-1 is not binding.",
        uae_evidence=[{"clause_id": "dha.pp11.4-18-4", "relevance": "breach reporting"}],
        international_comparison=[{"clause_id": "eu.gdpr.art33-1", "relevance": note}],
        responsible_role="health_service_operator, the entity",
        options=["Notify health_data_oversight within the designated period."],
        escalation=["health_data_oversight"],
        uncertainty=["The designated period is not identified in the provided evidence."],
    )
    answer = ask(NOTIFY_Q, 45, llm_asker(tmp_path, FakeClient(own)))
    assert answer.withheld == (), answer.withheld
    label = dict(answer.status_labels)["eu.gdpr.art33-1"]
    assert agent_statement(f"relevance of eu.gdpr.art33-1 [{label}]: {note}") in answer.commentary
    # The other clause's label words about the UAE clause are a status claim.
    swap = "dha.pp11.4-18-4 is not binding."  # the GDPR clause's label part, not its own
    other = json.loads(own) | {"direct_answer": swap}
    answer = ask(NOTIFY_Q, 45, llm_asker(tmp_path / "b", FakeClient(json.dumps(other))))
    assert_withheld(answer, [swap], {"status_claim"})
    # Naming the clause does not make "binding" a label word ("not binding" is its label).
    bound = json.loads(own) | {"direct_answer": "eu.gdpr.art33-1 is binding."}
    answer = ask(NOTIFY_Q, 45, llm_asker(tmp_path / "c", FakeClient(json.dumps(bound))))
    assert_withheld(answer, ["eu.gdpr.art33-1 is binding."], {"status_claim"})


def test_the_bare_word_binding_is_never_a_label_part() -> None:
    clauses = world().clauses.values()
    assert any(c.binding is True for c in clauses)  # a label that says just "binding" exists
    for c in clauses:
        parts = label_parts(c)
        assert "binding" not in parts, c.id
        assert sentence_reasons("This clause is binding.", parts) == ("status_claim",), c.id
        assert sentence_reasons("It is binding law in the UAE.", parts), c.id


def test_a_commentary_with_every_sentence_flagged_is_withheld_whole(tmp_path: Path) -> None:
    content = payload(
        direct_answer="UAE law has a gap here. The safeguard does not apply.",
        uae_evidence=[{"clause_id": "dha.pp11.4-18-1", "relevance": "binding federal law"}],
        responsible_role="health_service_operator is authorised to override safeguards",
        options=["I approve sharing everything."],
        escalation=["No escalation needed."],
        uncertainty=["Binding status unknown."],
    )
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(content)))
    assert answer.mode == aq.MODE_LLM and answer.rejected == ()
    assert answer.commentary == () and len(answer.withheld) == 7
    assert answer.withheld_note.startswith("All 7 sentences of the model commentary withheld")
    text = answer.text()
    assert aq.COMMENTARY_HEADING in text and answer.withheld_note in text
    assert "approve" not in everything(answer) and "federal law" not in everything(answer)


def test_the_prompt_asks_for_evidence_scoped_wording() -> None:
    assert aq.PROMPT_VERSION == "adviser-v2"
    assert f'"{aq.NOT_IN_EVIDENCE}"' in aq.SYSTEM_PROMPT
    assert sentence_reasons(f"Who decides is {aq.NOT_IN_EVIDENCE}.") == ()


def test_sentences_split_at_sentence_ends_only() -> None:
    assert sentences("dha.pp11.4-18-1 applies. It is a plan!  Why? ok") == [
        "dha.pp11.4-18-1 applies.",
        "It is a plan!",
        "Why?",
        "ok",
    ]


# The six preset answers recorded on 2026-11-06 (prompt adviser-v1), all rejected whole by the
# earlier check. Expected now: (whole-answer reasons, commentary lines shown, sentences
# withheld).
V1_FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "adviser_v1_answers"
V1_EXPECTED: dict[str, tuple[tuple[str, ...], int, int]] = {
    "preset-1.json": ((), 4, 10),  # its illus.* sentences are withheld
    "preset-2.json": (("abstention",), 0, 0),  # abstains yet cites a clause: structure fails
    "preset-3.json": ((), 6, 2),
    "preset-4.json": ((), 5, 2),
    "preset-5.json": ((), 4, 3),  # its illus.* sentences are withheld
    "preset-6.json": ((), 11, 6),  # the third international clause is not shown
}
# A sentence of each that must never be shown (a claim about the law or a status claim).
V1_NEVER_SHOWN = {
    "preset-1.json": "No listed clause authorises the telecom operator to share",
    "preset-2.json": "The clause does not specify an activation trigger",
    "preset-3.json": "no clause explicitly names a reversal decision-maker",
    "preset-4.json": "that period is not stated in the reviewed corpus",
    "preset-5.json": "their binding status in this simulation is not established",
    "preset-6.json": "so its legal weight is uncertain",
}


@pytest.mark.parametrize("name", sorted(V1_EXPECTED))
def test_the_six_recorded_v1_answers(tmp_path: Path, name: str) -> None:
    fixture = json.loads((V1_FIXTURES / name).read_text(encoding="utf-8"))
    presets = aq.load_presets(SCENARIOS_DIR / SCENARIO)
    assert (fixture["minute"], fixture["question"]) in presets
    assert fixture["prompt_version"] == "adviser-v1" and fixture["rejected"]  # rejected whole
    content = json.dumps(fixture["payload"])
    answer = ask(fixture["question"], fixture["minute"], llm_asker(tmp_path, FakeClient(content)))
    rejected, shown, withheld = V1_EXPECTED[name]
    assert answer.rejected == rejected
    assert answer.mode == (aq.MODE_TEMPLATE if rejected else aq.MODE_LLM)
    assert (len(answer.commentary), len(answer.withheld)) == (shown, withheld)
    assert V1_NEVER_SHOWN[name] not in everything(answer)
    for line in answer.commentary:  # every shown sentence passes the gap and authority checks
        body = line.removeprefix(AGENT_STATEMENT)
        for prefix in ("responsible role: ", aq.SUGGESTION, "escalation: ", "uncertainty: "):
            body = body.removeprefix(prefix)
        body = re.sub(r"^relevance of [\w.-]+: ", "", body)
        for sentence in sentences(body):
            assert not {"gap_wording", "authority_wording"} & set(sentence_reasons(sentence)), line


# --- Test-breaker round 1 (adviser-commentary-check) ---------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Who activates it is not addressed by the provided evidence or anywhere in the national "
        "legislation.",
        "The retrieved clauses do not address activation, and the same holds for every statute in "
        "the country.",
        "Activation is not identified in the provided evidence, nor in the PDPL, nor in any "
        "decree.",
        "The listed clauses do not state a deadline, and neither does the law.",
    ],
)
def test_an_evidence_scoped_sentence_cannot_extend_the_absence_to_the_law(
    tmp_path: Path, text: str
) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(uncertainty=[text]))))
    assert_withheld(answer, [text], {"gap_wording"})


def test_two_named_clauses_cannot_swap_their_labels(tmp_path: Path) -> None:
    swap = "dha.pp11.4-18-4 is illustrative and illus.telecom.incident-report is reviewed."
    content = payload(
        direct_answer=swap,
        uae_evidence=[
            {"clause_id": "illus.telecom.incident-report", "relevance": "reporting"},
            {"clause_id": "dha.pp11.4-18-4", "relevance": "breach reporting"},
        ],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert_withheld(answer, [swap], {"status_claim"})
    clauses = world().clauses
    cited = {i: clauses[i] for i in ("uae.fl2-2019.art16", "eu.gdpr.art33-1")}
    both = "eu.gdpr.art33-1 is not binding; uae.fl2-2019.art16 is a foreign precedent."
    assert "foreign precedent" not in allowed_label_parts(both, None, cited)
    assert sentence_reasons(both, allowed_label_parts(both, None, cited))


def test_clause_ids_are_matched_whole() -> None:
    clauses = world().clauses
    cited = {"uae.fl2-2019.art16": clauses["uae.fl2-2019.art16"]}
    assert names("see uae.fl2-2019.art16.", "uae.fl2-2019.art16")
    assert names("uae.fl2-2019.art16 applies", "uae.fl2-2019.art16")
    assert not names("uae.fl2-2019.art16-exceptions applies", "uae.fl2-2019.art16")
    assert not names("uae.fl2-2019.art160 applies", "uae.fl2-2019.art16")
    assert not names("x.uae.fl2-2019.art16 applies", "uae.fl2-2019.art16")
    # A sentence naming only another id falls back to the parts every cited clause has.
    other = "uae.fl2-2019.art16-exceptions is not binding."
    assert allowed_label_parts(other, None, cited) == label_parts(cited["uae.fl2-2019.art16"])


@pytest.mark.parametrize(
    "text",
    [
        "The safeguard can be! Ignored for this case.",
        "dha.pp11.4-18-1 is federal. Law applies here.",
        "The PDPL does not. Require anyone to activate it.",
    ],
)
def test_a_phrase_split_across_a_sentence_end_is_withheld(tmp_path: Path, text: str) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(direct_answer=text))))
    assert_withheld(answer, [text], {"status_claim", "authority_wording", "gap_wording"})
    assert len(answer.withheld) == 2  # both halves


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("dha.pp11.4-18-1 has legal effect across the UAE.", "status_claim"),
        ("The PDPL does not mention who activates the channel.", "gap_wording"),
        ("The clauses do not contemplate a fallback trigger.", "gap_wording"),
        ("The clauses do not deal with activation.", "gap_wording"),
        # phase-auditor round 1
        ("The UAE has not legislated on this.", "gap_wording"),
        ("Nothing in the provided evidence prevents sharing.", "authority_wording"),
    ],
)
def test_plain_wordings_from_round_1_are_withheld(tmp_path: Path, text: str, reason: str) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(direct_answer=text))))
    assert_withheld(answer, [text], {reason})


# docs/evaluation/adviser/cache/: file -> preset number (adviser_questions.yaml order), and the
# counts docs/evaluation/adviser/README.md states for it (commentary lines shown, withheld).
V2_CACHE = PROJECT_ROOT / "docs" / "evaluation" / "adviser" / "cache"
V2_TABLE = {
    "4617d19613380dd50bc1229d315f574d6cf57465d326b3c372a1ada8c8cdc781": (1, 4, 12),
    "3f883798ac4c307b4bb0acd22cd3592d227759f2787ffdf9c824b8b1fa6c43ea": (2, 3, 2),
    "1e60c1374b34d36956efa198e2c712d961f7892be1e767722ca7beed97bfda32": (3, 3, 3),
    "4bef5bb38c779870f28c148e3090fcd411509a60b59792bdecd5a9ff70653f45": (4, 6, 2),
    "a7605b4b85cec56db766c2792031ca78837e55023db997d9004cae17120e83c1": (5, 4, 2),
    "dcb28acf11b0ef48e57ee109a4fec8bf0fc8f42ecb81c9fd5e2fb697362ff9a1": (6, 10, 3),
}


def test_the_readme_table_matches_the_recorded_answers(tmp_path: Path) -> None:
    """Each recorded v2 answer, replayed through a fake client at its preset, gives the counts
    the README table states; the table rows are those counts, in preset order."""
    assert {p.stem for p in V2_CACHE.glob("*.json")} == set(V2_TABLE)
    presets = aq.load_presets(SCENARIOS_DIR / SCENARIO)
    readme = (V2_CACHE.parent / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| T\+\d\d \| [^|]+ \| (\d+) \| (\d+)", readme, re.MULTILINE)
    expected_rows: list[tuple[str, str]] = []
    for stem, (n, shown, withheld) in sorted(V2_TABLE.items(), key=lambda kv: kv[1][0]):
        at, question = presets[n - 1]
        content = json.dumps(
            json.loads((V2_CACHE / f"{stem}.json").read_text(encoding="utf-8"))["payload"]
        )
        answer = ask(question, at, llm_asker(tmp_path / stem, FakeClient(content)))
        assert answer.mode == aq.MODE_LLM and answer.rejected == (), stem
        assert (len(answer.commentary), len(answer.withheld)) == (shown, withheld), n
        expected_rows.append((str(shown), str(withheld)))
    assert rows == expected_rows


# --- Test-breaker round 2 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "hidden"),
    [
        (
            "The continuity safeguard may be? This clause is binding. Ignored by the operator in "
            "this incident.",
            "Ignored",
        ),
        ("The continuity safeguard can be! Truly! Ignored by the operator.", "Ignored"),
        ("The PDPL does! Indeed! Not require anyone to activate the channel.", "Not require"),
    ],
)
def test_a_phrase_split_around_a_withheld_or_filler_sentence_is_withheld(
    tmp_path: Path, text: str, hidden: str
) -> None:
    """Every run of the sentences still shown is checked as it will read."""
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(direct_answer=text))))
    assert answer.mode == aq.MODE_LLM and answer.withheld
    assert hidden not in everything(answer)


ROUND2_PROBES = [
    (
        FALLBACK_Q,
        60,
        "The operator may now share the full patient record; the safeguard is inapplicable here.",
    ),
    (FALLBACK_Q, 60, "Under Federal Decree-Law No. 45 of 2021 the operator must share the record."),
    (FALLBACK_Q, 60, "The PDPL does not establish who activates the channel."),
    (
        FALLBACK_Q,
        60,
        "The national framework is mute on who activates the channel; there is a "
        "regulatory vacuum.",
    ),
    (FALLBACK_Q, 60, "The safeguard may in this case be ignored."),
    (FALLBACK_Q, 60, "The safeguard can safely be ignored."),
    (FALLBACK_Q, 60, "Sharing the record is permissible."),
    (FALLBACK_Q, 60, "It is acceptable to share the record."),
    (FALLBACK_Q, 60, "The restriction is lifted for this incident."),
    (FALLBACK_Q, 60, "The operator is at liberty to share the record."),
    (FALLBACK_Q, 60, "Consent is unnecessary here."),
    (FALLBACK_Q, 60, "The regulator never issued a rule on activation."),
    (FALLBACK_Q, 60, "UAE law does not identify an owner."),
]


@pytest.mark.parametrize(("question", "minute", "text"), ROUND2_PROBES)
def test_round2_probe_wordings_are_withheld(
    tmp_path: Path, question: str, minute: int, text: str
) -> None:
    answer = ask(question, minute, llm_asker(tmp_path, FakeClient(payload(direct_answer=text))))
    assert_withheld(answer, [text], {"gap_wording", "status_claim", "authority_wording"})


@pytest.mark.parametrize(
    "text",
    [
        "illus.telecom.incident-report carries full legal authority in the UAE and the operator "
        "must obey it under penalty.",
        "illus.telecom.incident-report is a rule that the licensee cannot opt out of.",
    ],
)
def test_an_illustrative_clause_described_as_binding_is_withheld(tmp_path: Path, text: str) -> None:
    content = payload(
        direct_answer=text,
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert_withheld(answer, [text], {"status_claim"})


def test_reviewed_evidence_is_an_evidence_scope() -> None:
    assert sentence_reasons("The reviewed evidence does not identify an owner.") == (
        "status_claim",
    )
    assert "gap_wording" not in sentence_reasons(
        "The reviewed evidence does not identify an owner.", {"reviewed"}
    )


# --- Test-breaker round 3 ------------------------------------------------------------------------


def test_every_clause_named_in_the_commentary_has_its_status_label_shown(tmp_path: Path) -> None:
    """Preset 6 cites three international clauses; the sections show two. The commentary must not
    describe the third: no status label is shown for it."""
    stem = "dcb28acf11b0ef48e57ee109a4fec8bf0fc8f42ecb81c9fd5e2fb697362ff9a1"
    content = json.dumps(
        json.loads((V2_CACHE / f"{stem}.json").read_text(encoding="utf-8"))["payload"]
    )
    at, question = aq.load_presets(SCENARIOS_DIR / SCENARIO)[5]
    answer = ask(question, at, llm_asker(tmp_path, FakeClient(content)))
    labelled = dict(answer.status_labels)
    assert "oecd.ai-principles.accountability-cooperation" not in labelled
    for line in answer.commentary:
        for cid in world().clauses:
            if names(line, cid):
                assert cid in labelled, (cid, line)
    assert aq.CLAUSE_NOT_SHOWN in withheld_reasons(answer)


@pytest.mark.parametrize(
    "over",
    [
        {
            "escalation": [
                "The continuity safeguard can be",
                "ignored by the operator in this incident.",
            ]
        },
        {"options": ["The PDPL does"], "escalation": [], "uncertainty": ["not require it."]},
        {
            "direct_answer": "The adviser may",
            "responsible_role": "health_service_operator overrides",
        },
    ],
)
def test_a_phrase_split_across_fields_is_withheld(tmp_path: Path, over: dict[str, Any]) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(**over))))
    assert answer.withheld
    shown = " ".join(answer.commentary).casefold()
    assert "ignored" not in shown and "not require" not in shown and "overrides" not in shown


@pytest.mark.parametrize(
    "text",
    [
        "illus.telecom.incident-report is b" + chr(0x026A) + "nding.",  # small capital I
        "illus.telecom.incident-report is mandat" + chr(0x1D0F) + "ry.",  # small capital O
        "The adviser may overri" + chr(0x0501) + "e the safeguard for this incident.",  # komi de
    ],
)
def test_letters_outside_the_latin_blocks_are_withheld(tmp_path: Path, text: str) -> None:
    content = payload(
        direct_answer=text,
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert_withheld(answer, [text], {"unusual_letters"})


def test_a_long_commentary_is_checked_in_bounded_time(tmp_path: Path) -> None:
    import time

    long = " ".join(["The plan covers the channel."] * 200)
    started = time.perf_counter()
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload(uncertainty=[long]))))
    assert time.perf_counter() - started < 10, "the run re-check must stay bounded"
    assert answer.mode == aq.MODE_LLM and answer.withheld == ()


# --- Human decision 2026-11-06 (PR #35): no commentary about an illustrative clause ------------


STATUTE = "illus.telecom.incident-report is a statute every licensee in the UAE has to follow."


def test_a_sentence_naming_an_illustrative_clause_is_withheld(tmp_path: Path) -> None:
    """The reviewer's round-3 paraphrase: no phrase catches it; naming an illus.* id does."""
    assert not {"status_claim", "gap_wording", "authority_wording"} & set(sentence_reasons(STATUTE))
    content = payload(
        direct_answer=f"The operator reports within 60 minutes. {STATUTE}",
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert_withheld(answer, [STATUTE], {aq.ILLUSTRATIVE_CLAUSE})
    assert answer.commentary[0] == agent_statement("The operator reports within 60 minutes.")
    # Its relevance note names it too (the line is about that clause): withheld.
    assert not any("relevance of illus." in c for c in answer.commentary)
    assert answer.illustrative_note == aq.ILLUSTRATIVE_NOTE
    text = answer.text()
    assert text.index(aq.ILLUSTRATIVE_NOTE) > text.index(aq.COMMENTARY_HEADING)
    assert text.index(aq.ILLUSTRATIVE_NOTE) < text.index("Context (")


def test_no_illustrative_note_without_an_illustrative_clause(tmp_path: Path) -> None:
    answer = ask(FALLBACK_Q, 60, llm_asker(tmp_path, FakeClient(payload())))
    assert answer.mode == aq.MODE_LLM and answer.illustrative_note == ""
    assert aq.ILLUSTRATIVE_NOTE not in answer.text()
    template = ask(TELECOM_Q, 45, asker(tmp_path / "t"))  # template mode: no commentary block
    assert template.illustrative_note == "" and aq.ILLUSTRATIVE_NOTE not in template.text()


@pytest.mark.parametrize(
    "text",
    [
        "See ILLUS.telecom.incident-report.",
        "(illus.telecom.regulator-information-request) applies.",
    ],
)
def test_any_illustrative_id_form_is_withheld(tmp_path: Path, text: str) -> None:
    content = payload(
        direct_answer=text,
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert_withheld(answer, [text], {aq.ILLUSTRATIVE_CLAUSE, aq.CLAUSE_NOT_SHOWN})


# --- Test-breaker round 4 (final, scoped) --------------------------------------------------------


@pytest.mark.parametrize(
    "form",
    [
        "illus" + chr(0xFF0E) + "telecom.incident-report",  # full-width full stop
        "illus" + chr(0x2024) + "telecom.incident-report",  # one dot leader
        "Clause illus. telecom.incident-report",  # space after the dot
        "UAE-illus.telecom.incident-report",  # hyphen before
    ],
)
def test_an_illustrative_id_written_another_way_is_withheld(tmp_path: Path, form: str) -> None:
    """The sentence under test is the only extra withheld one (the illus.* relevance note is
    withheld in both runs), and its reason is the illus.* rule."""
    claim = form + STATUTE.removeprefix("illus.telecom.incident-report")
    base = {
        "uae_evidence": [{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        "responsible_role": "telecom_operator, the licensee",
    }
    plain = payload(direct_answer="The operator reports within 60 minutes.", **base)
    without = ask(TELECOM_Q, 45, llm_asker(tmp_path / "a", FakeClient(plain)))
    content = payload(direct_answer=f"The operator reports within 60 minutes. {claim}", **base)
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path / "b", FakeClient(content)))
    assert_withheld(answer, [claim], {aq.ILLUSTRATIVE_CLAUSE})
    extra = list(answer.withheld)
    for entry in without.withheld:
        extra.remove(entry)
    assert len(extra) == 1 and aq.ILLUSTRATIVE_CLAUSE in extra[0], extra


def test_an_own_label_relevance_note_survives_the_run_check(tmp_path: Path) -> None:
    note = "It is not binding."
    content = payload(
        direct_answer="The operator notifies within the designated period.",
        uae_evidence=[{"clause_id": "dha.pp11.4-18-4", "relevance": "breach reporting"}],
        international_comparison=[{"clause_id": "eu.gdpr.art33-1", "relevance": note}],
        responsible_role="health_service_operator, the entity",
        options=["Notify health_data_oversight within the designated period."],
        escalation=["health_data_oversight"],
        uncertainty=["The designated period is not identified in the provided evidence."],
    )
    answer = ask(NOTIFY_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    assert answer.withheld == (), answer.withheld
    assert any(c.endswith(note) for c in answer.commentary)


def test_the_trace_keeps_the_illustrative_and_withheld_notes(tmp_path: Path) -> None:
    content = payload(
        direct_answer=f"The operator reports within 60 minutes. {STATUTE}",
        uae_evidence=[{"clause_id": "illus.telecom.incident-report", "relevance": "reporting"}],
        responsible_role="telecom_operator, the licensee",
    )
    answer = ask(TELECOM_Q, 45, llm_asker(tmp_path, FakeClient(content)))
    trace = answer.trace()
    assert trace["illustrative_note"] == aq.ILLUSTRATIVE_NOTE
    assert trace["withheld_note"] == answer.withheld_note != ""
    assert aq.ILLUSTRATIVE_NOTE in json.dumps(trace, ensure_ascii=False)
