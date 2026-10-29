"""knowledge/retrieval.py: role clauses follow the engine's scope rule; extracted search never
touches the books and is deterministic."""

import json
import shutil
from pathlib import Path

from cascadeguard.cli import load_world, search_repairs
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.knowledge.loader import EXTRACTED_DIR, TRANSCRIPTIONS_DIR
from cascadeguard.knowledge.retrieval import (
    CONTEXT_LABEL,
    NOT_CITABLE_LABEL,
    NOT_SEARCHED,
    TRANSCRIPTION_CONTEXT_LABEL,
    WEB_CONTEXT_LABEL,
    clauses_for_role,
    extracted_digest,
    search_extracted,
)
from cascadeguard.simulation.replay import apply_repair

SUCCESS = (
    "owner.reverse_automated_lockouts.health_service_operator.30m"
    "+share.network_incident_status.telecom_operator.health_service_operator"
)


def test_role_clauses_are_exactly_what_the_role_may_cite() -> None:
    w = load_world("uae_health_access")
    book = RuleBook(w.clauses)
    for role in w.roles.roles:
        got = clauses_for_role(w.clauses, w.corpus_ids, role.id, role.allowed_actions)
        expected = sorted(
            cid for cid in w.clauses if book.concerns(cid, role.id, role.allowed_actions)
        )
        assert [c.id for c in got] == expected
        labels = dict((c.id, c.status_label) for c in w.clauses.values())
        assert all(c.status_label == labels[c.id] and c.citable for c in got)
    # Not every role sees every clause (the policy adviser does: provide_policy_analysis).
    sizes = {
        r.id: len(clauses_for_role(w.clauses, w.corpus_ids, r.id, r.allowed_actions))
        for r in w.roles.roles
    }
    assert min(sizes.values()) < len(w.clauses)


def test_repair_rules_are_shown_but_not_citable() -> None:
    w = load_world("uae_health_access")
    proposal = search_repairs("uae_health_access").comparison(SUCCESS).proposal
    _, roles, clauses = apply_repair(w.scenario, w.roles, w.clauses, proposal)
    health = roles.role("health_service_operator")
    got = clauses_for_role(clauses, w.corpus_ids, health.id, health.allowed_actions)
    repair = [c for c in got if c.id.startswith("repair.")]
    assert repair
    assert all(not c.citable and c.status_label == NOT_CITABLE_LABEL for c in repair)


def test_search_skips_books_and_is_deterministic(tmp_path: Path) -> None:
    rows = {
        "Some Policy.jsonl": [
            {"source_file": "Some Policy.pdf", "page": 2, "text": "incident report duty"}
        ],
        "Abhivardhan book.jsonl": [
            {"source_file": "Abhivardhan book.pdf", "page": 1, "text": "incident incident incident"}
        ],
        "Other.jsonl": [
            {"source_file": "The Oxford Handbook x.pdf", "page": 3, "text": "incident report"},
            {"source_file": "Other.pdf", "page": 1, "text": "incident"},
        ],
    }
    for name, pages in rows.items():
        (tmp_path / name).write_text("\n".join(json.dumps(p) for p in pages), encoding="utf-8")
    first = search_extracted("incident report", extracted_dir=tmp_path)
    assert first == search_extracted("incident report", extracted_dir=tmp_path)
    assert [(s.source_file, s.page) for s in first] == [("Some Policy.pdf", 2), ("Other.pdf", 1)]
    assert all(s.label == CONTEXT_LABEL for s in first)
    assert search_extracted("", extracted_dir=tmp_path) == ()


def test_search_on_the_real_extracted_text_never_returns_a_book() -> None:
    for s in search_extracted("artificial intelligence ethics governance", limit=50):
        assert "abhivardhan" not in s.source_file.casefold()
        assert "oxford handbook" not in s.source_file.casefold()


def test_web_transcription_snippets_carry_the_web_label(tmp_path: Path) -> None:
    """Human decision 2026-10-28: web pages are searched, and each web snippet says so."""
    rows = [
        {"source_file": "web/01_page.pdf", "page": 1, "text": "incident report", "web": True},
        {"source_file": "Law.pdf", "page": 4, "text": "incident report"},
    ]
    for name, row in zip(("01_page.jsonl", "Law.jsonl"), rows, strict=True):
        (tmp_path / name).write_text(json.dumps(row), encoding="utf-8")
    labels = {
        s.source_file: s.label for s in search_extracted("incident report", extracted_dir=tmp_path)
    }
    assert labels == {"web/01_page.pdf": WEB_CONTEXT_LABEL, "Law.pdf": CONTEXT_LABEL}
    assert WEB_CONTEXT_LABEL == "web transcription — unverified; context only; not citable"


def test_real_web_pages_are_searched_and_labelled() -> None:
    found = search_extracted("smart health services cybersecurity", limit=50)
    web = [s for s in found if s.source_file.startswith("web/")]
    assert web and all(s.label == WEB_CONTEXT_LABEL for s in web)
    assert all(s.label == CONTEXT_LABEL for s in found if s not in web)


TRA_STRATEGY = "UAE_National_Cybersecurity_Strategy.pdf"
NEWS_ITEM = "web/03_uae_national_cybersecurity_strategy.pdf"
CHARTER = "The UAE Charter for the Development and Use of Artificial Intelligence.pdf"
TRA_QUERIES = (
    "cyber security strategy",
    "information sharing exchange between tra and the entities",
    "incident response capabilities respond and recover",
    "critical sectors health",
    "telecommunications regulatory authority national",
)


def test_no_tra_era_strategy_snippet_reaches_extracted_context() -> None:
    """Human decision 2026-10-28: the TRA-era strategy is kept as provenance only. Its extracted
    text does match these queries, yet no snippet from it is ever returned."""
    assert {TRA_STRATEGY, NEWS_ITEM, CHARTER} == NOT_SEARCHED
    jsonl = EXTRACTED_DIR / TRA_STRATEGY.replace(".pdf", ".jsonl")
    pages = [json.loads(line) for line in jsonl.read_text("utf-8").splitlines() if line]
    for query in TRA_QUERIES:
        words = [w for w in query.split() if len(w) > 2]
        assert any(w in p["text"].casefold() for p in pages for w in words), query
        found = search_extracted(query, limit=1000)
        assert found, query
        assert all(s.source_file != TRA_STRATEGY for s in found), query


def test_no_snippet_of_the_news_item_on_the_2025_strategy_reaches_extracted_context() -> None:
    """Human decision 2026-10-29: web page 03 is a news item about the 2025 strategy, not its
    text, so it is never searched. (Until then a test here checked that it was searched.)"""
    jsonl = EXTRACTED_DIR / "03_uae_national_cybersecurity_strategy.jsonl"
    pages = [json.loads(line) for line in jsonl.read_text("utf-8").splitlines() if line]
    assert {p["source_file"] for p in pages} == {NEWS_ITEM}
    for query in (*TRA_QUERIES, "national cybersecurity strategy 2025"):
        assert all(s.source_file != NEWS_ITEM for s in search_extracted(query, limit=1000)), query
    assert any(w in p["text"].casefold() for p in pages for w in ("cybersecurity", "strategy")), (
        "the news item matches the queries, so excluding it is what keeps it out"
    )


def test_news_item_is_not_searched_under_any_file_name(tmp_path: Path) -> None:
    rows = {
        "Copy.jsonl": NEWS_ITEM,  # the record's own source_file is checked too
        "x.jsonl": "web/03_UAE_National_Cybersecurity_Strategy.PDF",
        "03_uae_national_cybersecurity_strategy.jsonl": "elsewhere.pdf",
        "Law.jsonl": "Law.pdf",
    }
    for name, source in rows.items():
        row = {"source_file": source, "page": 1, "text": "incident report"}
        (tmp_path / name).write_text(json.dumps(row), encoding="utf-8")
    found = search_extracted("incident report", extracted_dir=tmp_path)
    assert [s.source_file for s in found] == ["Law.pdf"]


def test_extracted_digest_ignores_the_news_item(tmp_path: Path) -> None:
    without = tmp_path / "without"
    shutil.copytree(EXTRACTED_DIR, without)
    (without / "03_uae_national_cybersecurity_strategy.jsonl").unlink()
    assert extracted_digest(without) == extracted_digest(EXTRACTED_DIR)


def test_tra_era_strategy_is_not_searched_under_any_file_name(tmp_path: Path) -> None:
    rows = {
        "UAE_National_Cybersecurity_Strategy.jsonl": TRA_STRATEGY,
        "Copy.jsonl": TRA_STRATEGY,  # the record's own source_file is checked too
        "uae_national_cybersecurity_strategy.jsonl": "uae_national_cybersecurity_strategy.pdf",
        "Law.jsonl": "Law.pdf",
    }
    for name, source in rows.items():
        row = {"source_file": source, "page": 1, "text": "incident report"}
        (tmp_path / name).write_text(json.dumps(row), encoding="utf-8")
    found = search_extracted("incident report", extracted_dir=tmp_path)
    assert [s.source_file for s in found] == ["Law.pdf"]


def test_extracted_digest_ignores_the_tra_era_strategy(tmp_path: Path) -> None:
    without = tmp_path / "without"
    shutil.copytree(EXTRACTED_DIR, without)
    (without / TRA_STRATEGY.replace(".pdf", ".jsonl")).unlink()
    assert extracted_digest(without) == extracted_digest(EXTRACTED_DIR)


def test_extracted_digest_follows_the_corpus_and_ignores_the_books(tmp_path: Path) -> None:
    def corpus(name: str, files: dict[str, str]) -> Path:
        d = tmp_path / name
        d.mkdir()
        for f, text in files.items():
            (d / f).write_text(json.dumps({"page": 1, "text": text}), encoding="utf-8")
        return d

    base = {"Law.jsonl": "a"}
    same = extracted_digest(corpus("a", base))
    assert same == extracted_digest(corpus("b", base))
    assert same == extracted_digest(corpus("c", {**base, "Abhivardhan book.jsonl": "x"}))
    assert same != extracted_digest(corpus("d", {**base, "01_page.jsonl": "web"}))
    assert same != extracted_digest(corpus("e", {"Law.jsonl": "b"}))


def test_extracted_digest_ignores_line_endings(tmp_path: Path) -> None:
    rows = [json.dumps({"source_file": "Law.pdf", "page": n, "text": "t"}) for n in (1, 2)]
    lf, crlf = tmp_path / "lf", tmp_path / "crlf"
    for d, end in ((lf, b"\n"), (crlf, b"\r\n")):
        d.mkdir()
        (d / "Law.jsonl").write_bytes(end.join(r.encode() for r in rows) + end)
    assert extracted_digest(lf) == extracted_digest(crlf)


def test_the_charter_text_layer_is_never_searched_only_reviewed_transcriptions() -> None:
    """Human decision 2026-10-29: the Charter's text layer is unreliable, so --extracted-context
    searches only its reviewed page-image transcriptions."""
    lines = (TRANSCRIPTIONS_DIR / f"{Path(CHARTER).stem}.jsonl").read_text("utf-8").splitlines()
    reviewed = sorted(r["page"] for r in map(json.loads, lines) if r["status"] == "reviewed")
    found = search_extracted("the uae and of", limit=1000)  # words on every Charter page
    charter = [s for s in found if s.source_file == CHARTER]
    assert sorted(s.page for s in charter) == reviewed and reviewed
    assert all(s.label == TRANSCRIPTION_CONTEXT_LABEL for s in charter)
    oversight = search_extracted("human oversight judgment errors biases", limit=1000)
    page4 = [s for s in oversight if s.source_file == CHARTER]
    assert all("oversight Al" not in s.text for s in page4)  # never the garbled text layer
    # Words only the text layer or a draft transcription has never match.
    assert not [s for s in search_extracted("theirreplaceablevalue", limit=1000)]
    assert not [
        s for s in search_extracted("peaceful coexistence", limit=1000) if s.source_file == CHARTER
    ]  # p.5: draft transcription


def test_only_reviewed_transcriptions_are_searched(tmp_path: Path) -> None:
    rows = [
        {
            "source_file": CHARTER,
            "page": 1,
            "text": "incident report",
            "transcribed": True,
            "status": "reviewed",
        },
        {
            "source_file": CHARTER,
            "page": 2,
            "text": "incident report",
            "transcribed": True,
            "status": "draft",
        },
        {"source_file": CHARTER, "page": 3, "text": "incident report", "status": "reviewed"},
        {
            "source_file": "Law.pdf",
            "page": 1,
            "text": "incident report",
            "transcribed": True,
            "status": "reviewed",
        },  # not a TRANSCRIBED_SOURCES file
    ]
    (tmp_path / "x.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    empty = tmp_path / "extracted"
    empty.mkdir()
    found = search_extracted("incident report", extracted_dir=empty, transcriptions_dir=tmp_path)
    assert [(s.source_file, s.page) for s in found] == [(CHARTER, 1)]


def test_extracted_digest_follows_reviewed_transcriptions_only(tmp_path: Path) -> None:
    none = tmp_path / "none"
    none.mkdir()
    base = extracted_digest(EXTRACTED_DIR, none)
    draft = tmp_path / "draft"
    draft.mkdir()
    row = {"source_file": CHARTER, "page": 2, "text": "x", "transcribed": True, "status": "draft"}
    (draft / "c.jsonl").write_text(json.dumps(row), encoding="utf-8")
    assert extracted_digest(EXTRACTED_DIR, draft) == base
    assert extracted_digest(EXTRACTED_DIR, TRANSCRIPTIONS_DIR) != base  # p.4 is reviewed
