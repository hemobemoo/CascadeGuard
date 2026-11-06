"""The technical report (docs/report/): every number and id traced to the committed data, the
approved wording kept, the .docx equal to the Markdown, the committed PDF at most 5 pages."""

import importlib.util
import itertools
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from cascadeguard.domain.policies import is_uae_jurisdiction
from cascadeguard.domain.repairs import RepairOperationType
from cascadeguard.engine.constraints import GAP_CLAIM, OVERSTATED
from cascadeguard.knowledge.loader import PROJECT_ROOT, load_clauses, load_gap_example_clauses
from cascadeguard.storage.reports import (
    CONCLUSION_DRAFT,
    NO_EXAMPLE,
    ScriptedRuns,
    load_gap_examples,
    load_gate4,
    scripted_runs,
)

REPORT = PROJECT_ROOT / "docs" / "report"
SOURCE = REPORT / "cascadeguard-report.md"
DOCX = REPORT / "cascadeguard-report.docx"
PDF = (
    REPORT / "cascadeguard-report.pdf"
)  # the designed PDF (scripts/report_pdf), linked in the README
MAX_PAGES = 5  # the organizers' limit
# Approved phrases (gate 7, human 2026-10-31), reused word for word.
KEY_PHRASES = (
    "applied without the authority the governed engine requires",
    "masked, cause still present",
    "needs human and institutional approval",
    "candidate gap for expert review, not a confirmed legal or standards gap",
    "hypothetical rules, not source clauses",
    "decision support, not legal interpretation",
)
# Numbers that are labels, not data: section numbers, standard and report names, the review date,
# the contact address. Everything else must come from the data (`traced`).
LABEL_NUMBERS = {
    "1",  # section numbers 1-6 and the Y.3172 sentence
    "2",
    "3",
    "4",
    "5",
    "6",
    "2.0",  # "AI Readiness 2.0"
    "3172",  # ITU-T Y.3172
    "2026-10-31",  # the gate-7 review dates
    "2026-11-06",
    "7",  # "gate 7", the human review gate
}


NUMBER = r"(?<![\w.])\d[\d,.]*\d|(?<![\w.])\d"
# The precedents paragraph (organizer question "Was there such an incident before?"): its numbers
# describe real, analogous incidents, so they trace to docs/report/background-sources.yaml, not
# to the scenario data. Approved by the human (gates 7/8, 2026-11-04); the draft file keeps a copy.
BACKGROUND_MARKER = "**Precedents.**"
BACKGROUND_SOURCES = REPORT / "background-sources.yaml"
BACKGROUND_DRAFT = PROJECT_ROOT / "docs" / "review" / "report-background-draft.md"
# The brief said "max ~120 words"; the human-approved paragraph (2026-11-04) is 122.
BACKGROUND_MAX_WORDS = 125
MAX_QUOTE_WORDS = 15


def text() -> str:
    return SOURCE.read_text(encoding="utf-8")


def background_paragraphs(t: str) -> list[str]:
    return [p for p in t.replace("\r\n", "\n").split("\n\n") if p.startswith(BACKGROUND_MARKER)]


def background_facts() -> list[dict[str, Any]]:
    return yaml.safe_load(BACKGROUND_SOURCES.read_text(encoding="utf-8"))["facts"]


@pytest.fixture(scope="module")
def runs() -> ScriptedRuns:
    return scripted_runs()


def traced(runs: ScriptedRuns) -> dict[str, str]:
    """Every number the report may state, with where it comes from."""
    b, off, rep = runs.baseline, runs.governance, runs.rank1
    scenario = (PROJECT_ROOT / "scenarios" / "uae_health_access" / "scenario.yaml").read_text(
        encoding="utf-8"
    )
    statuses = [label.split(" ")[0] for _, label in b.loaded_clauses]
    live_base, live_off = load_gate4()
    out: dict[str, str] = {}

    def add(value: object, source: str) -> None:
        out[str(value)] = source

    for m in re.findall(r"\b\d{1,3},\d{3}\b", scenario):
        add(m, "scenario.yaml fact")
    add(65, "scenario.yaml: users aged over 65")
    for e in runs.world.scenario.events:
        add(f"{e.at_minute:02d}", "inject minute")
        add(e.at_minute, "inject minute")
    add(len(b.failures), "scripted baseline failures")
    add(len(b.loaded_clauses), "loaded clauses")
    add(statuses.count("reviewed"), "loaded reviewed clauses")
    add(statuses.count("illustrative"), "loaded illustrative clauses")
    add(len(runs.search.ranked), "ranked repairs")
    add(sum(1 for c in runs.search.ranked if not c.unmet_critical_goals), "resolved repairs")
    add(len(rep.removed), "rank-1 removed")
    add(len(rep.masked), "rank-1 masked")
    add(len(rep.proposal.edits), "rank-1 edits")
    for edit in rep.proposal.edits:
        if edit.deadline_minutes is not None:
            add(edit.deadline_minutes, "rank-1 owner deadline")
    add(len(off.ungoverned.failures), "ungoverned failures")
    add(len(off.masked()), "ungoverned masked")
    add(len(runs.world.roles.roles), "institutional roles")
    add(len(live_base["failures"]), "live governed failures")
    for w in live_off["would_have_been_rejected"]:
        add(w["minute"], "live waived minute")
    return out


CITED_TABLE_START = "**Policy documents loaded and cited by the agents.**"


def cited_block(t: str) -> str:
    """§4's cited-documents block: its lead paragraph, table and note, up to section 5."""
    if CITED_TABLE_START not in t:
        return ""
    return CITED_TABLE_START + t.split(CITED_TABLE_START, 1)[1].split("## 5.", 1)[0]


def cited_numbers() -> dict[str, str]:
    """Numbers the cited-documents block may state, from the citation map only."""
    cmap = _citation_map()
    out: dict[str, str] = {}
    for counts in cmap.document_counts().values():
        for run in cmap.RUNS:
            out[str(counts[run])] = f"citation map: {run} citations of a document"
    out[str(cmap.shared_live_steps()[0])] = "citation map: decisions shared by the live runs"
    for n in _rejected_per_live_run(cmap).values():
        out[str(n)] = "citation map: rejected decisions per live run"
    return out


def _rejected_per_live_run(cmap: Any) -> dict[str, int]:
    steps: dict[str, set[tuple[str, int]]] = {
        cmap.LIVE_GOVERNED: set(),
        cmap.LIVE_UNGOVERNED: set(),
    }
    for c in cmap.all_citations():
        if c.verdict != "accepted" and c.run in steps:
            steps[c.run].add((c.role, c.minute))
    return {run: len(s) for run, s in steps.items()}


# §4 "Policy documents loaded and cited by the agents": report row -> source file (None =
# illustrative).
CITED_DOCUMENTS: dict[str, str | None] = {
    "UAE Federal Law on ICT in Health Fields (English translation)": (
        "UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf"
    ),
    "DHA Health Data Protection and Confidentiality Policy": (
        "Health Data Protection and Confidentiality Policy_EN2022810559.pdf"
    ),
    "Illustrative telecom rules (synthetic, no source document)": None,
    "UAE Charter for the Development and Use of AI": (
        "The UAE Charter for the Development and Use of Artificial Intelligence.pdf"
    ),
    "UAE Personal Data Protection Law (PDPL, English translation)": (
        "Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf"
    ),
    "EU General Data Protection Regulation (GDPR)": "GDPR-Regulation (EU) 2016-679.pdf",
    "OECD Recommendation on Artificial Intelligence": "OECD_Recommendation_AI.pdf",
    "UNESCO Recommendation on the Ethics of AI": (
        "UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf"
    ),
    "MOHAP smart health and AI policy (web transcription)": (
        "web/01_uae_smart_health_ai_policy.pdf"
    ),
}


def _citation_map() -> Any:
    spec = importlib.util.spec_from_file_location(
        "citation_map", PROJECT_ROOT / "scripts" / "citation_map.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_cited_documents_table_matches_the_citation_map() -> None:
    """Every document with loaded clauses has one row; its binding cell, use and three per-run
    counts equal the citation map (never a single total); the live runs' shared decisions and the
    one rejected decision are stated as such."""
    cmap = _citation_map()
    counts = cmap.document_counts()
    assert set(CITED_DOCUMENTS.values()) == set(counts)
    section4 = text().split("## 4.", 1)[1].split("## 5.", 1)[0]
    rows = {
        cells[0]: cells
        for line in section4.splitlines()
        if line.startswith("| ")
        for cells in [[c.strip() for c in line.strip().strip("|").split("|")]]
    }
    header = rows.pop("Document")
    assert header[2:] == [
        "Binding in the UAE",
        "How it is used",
        "Scripted",
        "Live governed",
        "Live ungoverned",
    ]
    examples = {
        str(e["clause"])
        for e in yaml.safe_load(
            (PROJECT_ROOT / "scenarios" / "uae_health_access" / "gap_examples.yaml").read_text(
                encoding="utf-8"
            )
        )["entries"]
    }
    loaded = load_clauses()
    for name, source in CITED_DOCUMENTS.items():
        cells = rows[name]
        n = counts[source]
        assert cells[4:] == [str(n[r]) for r in cmap.RUNS], name
        assert cells[2] == cmap.document_binding(source), name
        uses: list[str] = []
        if sum(n.values()):
            uses.append("cited by agents")
        mapped = [c for c in loaded if c.id in examples and c.source_file == source]
        if mapped:  # gap_examples.yaml: "global and UAE-principle examples"
            uae = all(is_uae_jurisdiction(c.jurisdiction) for c in mapped)
            kind = "UAE-principle" if uae else "global"
            uses.append(f"{kind} example in the gap analysis")
        assert cells[3] == ("; ".join(uses) or "loaded, not cited"), name
    shared, _ = cmap.shared_live_steps()
    assert f"The two live runs share {shared} decisions" in section4
    per_run = set(_rejected_per_live_run(cmap).values())
    assert len(per_run) == 1, per_run
    assert f"{per_run.pop()} decision rejected (citation out of scope)" in section4
    assert "docs/citation-map.md" in section4
    assert (
        "binding means binding in the UAE, as recorded on each clause; it does not mean the "
        "document applies to this scenario." in section4
    )
    rejected = {(c.run, c.role, c.minute) for c in cmap.all_citations() if c.verdict != "accepted"}
    assert rejected == {
        (cmap.LIVE_GOVERNED, "telecom_operator", 75),
        (cmap.LIVE_UNGOVERNED, "telecom_operator", 75),
    }


def test_every_number_is_traced_to_the_data(runs: ScriptedRuns) -> None:
    allowed = traced(runs)
    body = text().replace("\r\n", "\n")
    for paragraph in background_paragraphs(body):  # checked against its sources instead
        body = body.replace(paragraph, "")
    block = cited_block(body)  # checked against the citation map only
    if block:
        body = body.replace(block, "")
        others = {
            **cited_numbers(),
            **{f"{e.at_minute}": "inject minute" for e in runs.world.scenario.events},
        }
        stray = [
            n
            for n in re.findall(NUMBER, re.sub(r"`[^`]+`", "", block))
            if n.rstrip(".,") not in others and n.rstrip(".,") not in LABEL_NUMBERS
        ]
        assert not stray, f"cited-documents numbers not from the citation map: {sorted(set(stray))}"
    body = re.sub(r"`[^`]+`", "", body)  # ids are checked separately
    body = re.sub(r"\S+@\S+|https?://\S+", "", body)  # contact address and links
    body = body.replace("2026-10-31", "").replace("2026-11-06", "")
    untraced = [
        n
        for n in re.findall(NUMBER, body)
        if n.rstrip(".,") not in allowed and n.rstrip(".,") not in LABEL_NUMBERS
    ]
    assert not untraced, f"numbers not traced to the data: {sorted(set(untraced))}"


def _unsourced(paragraph: str, facts: list[dict[str, Any]]) -> list[str]:
    """Numbers in the paragraph not listed for any fact whose markers all appear in it."""
    present = [f for f in facts if all(m in paragraph for m in f["markers"])]
    sourced = {str(n) for f in present for n in f["numbers"]}
    return [n for n in re.findall(NUMBER, paragraph) if n.rstrip(".,") not in sourced]


def test_background_numbers_come_from_the_background_sources() -> None:
    facts = background_facts()
    drafts = background_paragraphs(BACKGROUND_DRAFT.read_text(encoding="utf-8"))
    assert len(drafts) == 1, "the draft holds exactly one precedents paragraph"
    assert len(background_paragraphs(text())) <= 1
    for paragraph in drafts + background_paragraphs(text()):
        assert re.findall(NUMBER, paragraph), "the check must see the paragraph's numbers"
        assert not _unsourced(paragraph, facts), _unsourced(paragraph, facts)


def test_a_number_without_its_claim_is_refused() -> None:
    """The rule is per claim: a sourced number fails once its claim's markers are absent, and an
    unlisted number fails even next to a sourced claim."""
    facts = background_facts()
    assert _unsourced(f"{BACKGROUND_MARKER} Optus 2023: 10.2 million.", facts) == []
    assert _unsourced(f"{BACKGROUND_MARKER} An outage hit 10.2 million.", facts) == ["10.2"]
    assert _unsourced(f"{BACKGROUND_MARKER} Optus 2023: 11 million.", facts) == ["11"]
    # Every fact needs at least two markers, so a bare name does not unlock its numbers.
    assert all(len(f["markers"]) >= 2 for f in facts)
    assert _unsourced(f"{BACKGROUND_MARKER} Bank of America lost 100 days.", facts) == ["100"]


def test_background_sources_are_complete() -> None:
    facts = background_facts()
    ids = [f["id"] for f in facts]
    assert len(ids) == len(set(ids))
    for f in facts:
        for key in ("claim", "source_title", "publisher", "source_type", "read_via"):
            assert str(f[key]).strip(), (f["id"], key)
        assert f["url"].startswith("https://"), f["id"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", f["retrieved"]), f["id"]
        assert f["markers"], f["id"]
        for n in f["numbers"]:  # every listed number is stated in the claim itself
            assert re.search(rf"(?<![\w.]){re.escape(str(n))}(?![\d])", f["claim"]), (f["id"], n)
    # Background only: never a clause, never read by the engine.
    assert not BACKGROUND_SOURCES.is_relative_to(PROJECT_ROOT / "policies")
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        assert "background-sources" not in path.read_text(encoding="utf-8"), path


def test_the_background_wording_follows_the_rules() -> None:
    for paragraph in background_paragraphs(BACKGROUND_DRAFT.read_text(encoding="utf-8")) + (
        background_paragraphs(text())
    ):
        assert len(paragraph.split()) <= BACKGROUND_MAX_WORDS, len(paragraph.split())
        lower = paragraph.lower()
        assert "analogous" in lower and "not this scenario" in lower
        assert "hypothetical" in lower and "synthetic" in lower
        assert not GAP_CLAIM.search(paragraph), GAP_CLAIM.findall(paragraph)
        assert not OVERSTATED.search(paragraph), OVERSTATED.findall(paragraph)
        for quote in re.findall(r"[\"“]([^\"”]+)[\"”]", paragraph):  # not apostrophes
            assert len(quote.split()) <= MAX_QUOTE_WORDS, quote


def test_the_stated_facts_match_the_runs(runs: ScriptedRuns) -> None:
    t = text()
    b, off, rep = runs.baseline, runs.governance, runs.rank1
    live_base, live_off = load_gate4()
    assert f"diagnoses {len(b.failures)} coordination failures" in t
    assert all(f"`{f.subject}`" in t or f.subject in t for f in b.failures if "->" not in f.subject)
    assert len(runs.world.roles.roles) == 6 and "Six institutional roles" in t
    assert len(list(RepairOperationType)) == 5 and "five edit types" in t
    # The three scripted runs.
    goals = {
        "Governed": dict(b.goals),
        "Ungoverned": dict(off.ungoverned.goals),
        "Governed + rank-1": dict(rep.replay.goals),
    }

    def cell(m: int | None) -> str:
        return f"met at T+{m}" if m is not None else "unmet"

    rows = {line.split("|")[1].strip(): line for line in t.splitlines() if line.startswith("| ")}
    for name, g in goals.items():
        row = next(v for k, v in rows.items() if k.startswith(name))
        assert (
            f"| {cell(g['patient_access_restored'])} | {cell(g['alert_cause_known_to_health'])} |"
            in row
        )
    waived = off.waived()
    assert len(waived) == 3 and {w["minute"] for w in waived} == {60}
    assert all(f"`{w['action']}`" in t for w in waived)
    assert rep.outcome == "resolved" and not rep.unmet_critical_goals
    assert rep.proposal.requires_authorization
    assert all(f"`{m}`" in t for m in rep.masked)
    assert f"Of {len(runs.search.ranked)} ranked repairs, 2 meet every critical goal" in t
    # Live (gate 4): the same failures, the goal met at T+15 by the waived fallback activation.
    assert sorted(f["id"] for f in live_base["failures"]) == sorted(f.id for f in b.failures)
    assert live_off["ungoverned_run"]["goals"]["patient_access_restored"] == "met at T+15"
    assert {w["action"] for w in live_off["would_have_been_rejected"]} == {
        "activate_fallback_channel"
    }
    assert "No live repair was run." in t


def test_every_backticked_id_exists(runs: ScriptedRuns) -> None:
    loaded = {cid for cid, _ in runs.baseline.loaded_clauses}
    corpus = {c.id: c for c in load_clauses()}
    known = (
        loaded
        | {f.id for f in runs.baseline.failures}
        | {g for g, _ in runs.baseline.goals}
        | {a.id for a in runs.world.roles.actions}
        | {r.id for r in runs.world.roles.roles}
        | {"RoleView"}
        | set(load_gap_example_clauses())  # shown as gap examples only, never loaded
    )
    for token in re.findall(r"`([^`]+)`", text()):
        if token.startswith(("uv ", "illus.telecom.*")) or token == "illus.telecom.*":
            continue
        if token.endswith(".*"):
            matches = [c for c in loaded if c.startswith(token[:-1])]
            assert matches, token
            continue
        assert token in known, token
        if token in corpus:  # a clause: loaded (reviewed or illustrative), never a draft
            assert token in loaded, token


# The bullets of the policy-gaps section, by heading, and the diagnosed failure each one is about.
GAP_BULLETS = {
    "Information deadlock (network status to the health operator).": (
        "information_deadlock:network_incident_status->health_service_operator"
    ),
    "Orphan duty: reversing automated lockouts.": "orphan_duty:reverse_automated_lockouts",
    "Orphan duty: activating the fallback channel.": "orphan_duty:activate_fallback_channel",
    "Undefined trigger: reviewing automated lockouts.": (
        "undefined_trigger:review_automated_lockouts"
    ),
}


def gap_bullets(report: str) -> dict[str, str]:
    """The policy-gaps section's bullets, keyed by their bold heading."""
    section = report.replace("\r\n", "\n").split("## 6.", 1)[1]
    out: dict[str, str] = {}
    for line in section.splitlines():
        m = re.match(r"- \*\*(.+?)\*\* (.*)", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def example_mismatches(report: str, failures: set[str]) -> list[str]:
    """Why the policy-gaps section disagrees with gap_examples.yaml (empty when it agrees): each
    bullet must name exactly the clauses mapped to its failure (after the word "Example" or
    "Examples"), and say NO_EXAMPLE only when nothing is mapped."""
    bullets = gap_bullets(report)
    problems: list[str] = []
    if set(bullets) != set(GAP_BULLETS):
        problems.append(f"bullet headings {sorted(bullets)}")
    if set(GAP_BULLETS.values()) != failures:
        problems.append(f"diagnosed failures {sorted(failures)}")
    mapped: dict[str, set[str]] = {}
    for e in load_gap_examples().entries:
        if e.approved:
            mapped.setdefault(e.failure, set()).add(e.clause)
    for heading, failure in GAP_BULLETS.items():
        body = bullets.get(heading, "")
        expected = mapped.get(failure, set())
        if named_examples(body) != expected:
            problems.append(
                f"{heading} names {sorted(named_examples(body))}, not {sorted(expected)}"
            )
        if (NO_EXAMPLE in body) != (not expected):
            problems.append(f"{heading}: the no-example sentence")
    return problems


def test_the_named_examples_match_the_reviewed_mapping(runs: ScriptedRuns) -> None:
    """The report's policy-gaps bullets name the reviewed mapping, so the text cannot go stale."""
    assert example_mismatches(text(), {f.id for f in runs.baseline.failures}) == []


def named_examples(body: str) -> set[str]:
    """The ids a bullet names after the word "Example"/"Examples" (none if it has no such word)."""
    found = re.search(r"\bExamples?\b", body)
    return set(re.findall(r"`([^`]+)`", body[found.start() :])) if found else set()


def test_the_example_check_catches_the_old_sentence(runs: ScriptedRuns) -> None:
    """The report with its fallback bullet as submitted before the 2026-11-06 mapping fails the
    same check the real report passes."""
    report = text().replace("\r\n", "\n")
    heading = "- **Orphan duty: activating the fallback channel.** "
    start = report.index(heading)
    end = report.index("\n", start)
    old = (
        heading + "Only uncertain authority was found (`dha.pp11.4-18-1`, binding unknown); it "
        "requires a determination. No reviewed example clause is mapped to this failure. The "
        "rank-1 repair only masks it: it stays open for the authorities to determine."
    )
    stale = report[:start] + old + report[end:]
    problems = example_mismatches(stale, {f.id for f in runs.baseline.failures})
    assert len(problems) == 2 and all("activating the fallback channel" in p for p in problems)


def test_the_approved_wording_is_kept() -> None:
    t = text()
    for phrase in KEY_PHRASES:
        assert phrase in t, phrase
    assert "unauthori" not in t.lower()
    assert "hypothetical" in t and "not binding" in t
    free = t
    for phrase in KEY_PHRASES:
        free = free.replace(phrase, "")
    assert not OVERSTATED.search(free), OVERSTATED.findall(free)
    # Live numbers are always labelled live; scripted runs are labelled scripted.
    section5 = t.split("## 5.", 1)[1].split("## 6.", 1)[0]
    assert "T+15" in section5
    for paragraph in section5.split("\n\n"):
        if "T+15" in paragraph:
            assert "live" in paragraph.lower(), paragraph


def test_the_contact_address_is_in_the_report_only() -> None:
    assert "@" in text().split("## 1.", 1)[0]
    assert not re.search(r"\S+@\S+\.\w+", (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"))


def _builder() -> Any:
    spec = importlib.util.spec_from_file_location(
        "report_docx", PROJECT_ROOT / "scripts" / "report_docx.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_docx_says_what_the_markdown_says() -> None:
    from docx import Document

    builder = _builder()
    report = builder.parse(text())
    doc = Document(str(DOCX))
    words = " ".join(p.text for p in doc.paragraphs)
    words += " " + " ".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    words = " ".join(words.split())
    assert report.title in words
    for section in report.sections:
        assert section.title in words, section.title
        for kind, content in section.blocks:
            if kind == "table":
                for row in content:
                    for cell in row:
                        assert " ".join(builder.plain(cell).split()) in words, cell
            else:
                assert " ".join(builder.plain(str(content)).split()) in words, content


def test_the_docx_is_a4_and_its_tables_fit_the_margins() -> None:
    from docx import Document

    builder = _builder()
    doc = Document(str(DOCX))
    page = doc.sections[0]
    assert page.page_width and page.page_height
    assert (page.page_width.twips, page.page_height.twips) == (11906, 16838)  # A4
    width = builder.text_width(doc)
    for table in doc.tables:
        grid = sum(builder.grid_widths(table))
        assert grid <= width + 4, (grid, width)  # rounding of the scaled columns


@pytest.mark.parametrize(
    ("pdf_path", "how"),
    [
        (PDF, "build it: uv run python scripts/report_pdf/build.py"),
    ],
    ids=["designed"],
)
def test_the_pdf_is_at_most_five_pages_and_current(pdf_path: Path, how: str) -> None:
    import pdfplumber

    assert pdf_path.exists(), f"{pdf_path.name} is missing; {how}"
    with pdfplumber.open(pdf_path) as pdf:
        assert len(pdf.pages) <= MAX_PAGES, len(pdf.pages)
        for p in pdf.pages:  # A4 in points
            assert abs(p.width - 595.3) < 1 and abs(p.height - 841.9) < 1, (p.width, p.height)
        pages = " ".join((p.extract_text() or "") for p in pdf.pages)

    def flatten(s: str) -> str:  # a line break after a hyphen extracts as "- "
        return re.sub(r"-\s+", "-", " ".join(s.split()))

    flat = flatten(pages)
    builder = _builder()
    report = builder.parse(text())
    for section in report.sections:
        assert section.title.split(",")[0] in flat, section.title
    for value in ("4,812", "3,950", "T+15", "T+60", "T+30"):
        assert value in flat, value
    # Current: every paragraph and bullet of the Markdown, word for word (table cells wrap in
    # extraction, so they are left to the .docx test). A stale export fails here.
    for section in report.sections:
        for kind, content in section.blocks:
            if kind != "table":
                paragraph = flatten(builder.plain(str(content)))
                assert paragraph in flat, f"{pdf_path.name} is stale ({how}): {paragraph[:60]}"


def _pdf_builder() -> Any:
    spec = importlib.util.spec_from_file_location(
        "report_pdf_build", PROJECT_ROOT / "scripts" / "report_pdf" / "build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flatten(s: str) -> str:  # a line break after a hyphen extracts as "- "
    return re.sub(r"-\s+", "-", " ".join(s.split()))


def _columns(anchors: list[str], depth: float, centred: bool) -> list[str]:
    """The PDF text under each anchor word of one row, one string per column.

    Figures set side by side extract line by line across all of them, so each column is cropped
    on its own: from the anchor's top down `depth` points, split halfway between centred anchors
    or at the next left-aligned anchor.
    """
    import pdfplumber

    with pdfplumber.open(PDF) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for first in (w for w in words if w["text"] == anchors[0]):
                row = [first]
                for anchor in anchors[1:]:
                    nxt = next(
                        (
                            w
                            for w in words
                            if w["text"] == anchor
                            and abs(w["top"] - first["top"]) < 2
                            and w["x0"] > row[-1]["x0"]
                        ),
                        None,
                    )
                    if nxt is None:
                        break
                    row.append(nxt)
                if len(row) < len(anchors):
                    continue
                if centred:
                    mids = [(w["x0"] + w["x1"]) / 2 for w in row]
                    cuts = [(a + b) / 2 for a, b in itertools.pairwise(mids)]
                    edges = [mids[0] - (cuts[0] - mids[0]), *cuts, mids[-1] + mids[-1] - cuts[-1]]
                else:
                    edges = [w["x0"] - 2 for w in row] + [float(page.width)]
                top = first["top"] - 1
                return [
                    _flatten(page.crop((left, top, right, top + depth)).extract_text() or "")
                    for left, right in itertools.pairwise(edges)
                ]
    raise AssertionError(f"row not found in the PDF: {anchors}")


def test_the_pdf_figures_restate_the_data(runs: ScriptedRuns) -> None:
    """The text the PDF adds to the Markdown (key figures, timeline, Y.3172 diagram) is read from
    scripts/report_pdf/build.py, traced to the data, and found in the committed PDF, so the
    script, the data and the PDF cannot drift apart."""
    build = _pdf_builder()
    allowed = traced(runs)
    b = runs.baseline
    t = text()
    labels = [f"{n} {c}" for n, c in build.KEY_FIGURES]
    labels += [f"{time} {label}" for time, label, _ in build.TIMELINE]
    labels += [f"{node} {label}" for node, label, _ in build.PIPELINE]
    labels += [build.MLFO_BAND, build.SANDBOX_BAND, build.PROPOSAL_NOTE]
    for label in labels:  # every number traced, as in the Markdown
        for n in re.findall(r"(?<![\w.+])\d[\d,]*\d|(?<![\w.+])\d", label):
            assert n in allowed, (n, label)

    # Key figures: each number with its own source and its qualification.
    figures = dict(build.KEY_FIGURES)
    events = {e.at_minute: e.model_dump_json() for e in runs.world.scenario.events}
    assert "4,812" in events[15] and "(T+15)" in figures["4,812"]
    assert "3,950" in events[60] and "T+60" in figures["3,950"]
    assert figures[str(len(b.failures))].endswith("in the baseline (candidate gaps)")
    statuses = [label.split(" ")[0] for _, label in b.loaded_clauses]
    assert figures[str(len(b.loaded_clauses))] == (
        f"clauses loaded: {statuses.count('reviewed')} reviewed, "
        f"{statuses.count('illustrative')} illustrative, drafts never"
    )
    assert "draft" not in statuses
    resolved = sum(1 for c in runs.search.ranked if not c.unmet_critical_goals)
    assert figures[f"{resolved} of {len(runs.search.ranked)}"] == (
        "ranked repairs meet every critical goal (scripted agents)"
    )

    # Timeline: one stop per inject, in order; each label's numbers are in the §2 sentence that
    # ends at that time.
    times = [time for time, _, _ in build.TIMELINE]
    assert times == [f"T+{e.at_minute:02d}" for e in runs.world.scenario.events]
    use_case = t.split("## 2.", 1)[1].split("**Gaps", 1)[0]
    for time, label, _ in build.TIMELINE:
        before = use_case.split(f"({time})", 1)[0].rsplit(")", 1)[-1]
        assert time in use_case, time
        for n in re.findall(r"\d[\d,]*\d", label):
            assert n in before, (n, label)

    # Y.3172 diagram: the §4 table's nodes in order, MLFO and Sandbox as the two bands.
    table = [line.split("|")[1].strip() for line in t.splitlines() if line.startswith("| ")]
    nodes = table[1 : table.index("MLFO")]
    assert [node for node, _, _ in build.PIPELINE] == nodes
    assert dict((n, label) for n, label, _ in build.PIPELINE)["M"] == (
        f"{len(runs.world.roles.roles)} role agents"
    )
    assert table[table.index("MLFO") : table.index("Sandbox") + 1] == ["MLFO", "Sandbox"]
    assert build.MLFO_BAND.startswith("MLFO · ") and build.SANDBOX_BAND.startswith("Sandbox · ")
    for phrase in (
        "deterministic orchestrator (not an agent)",
        "repair search over the closed grammar",
        "replay of the identical incident with a candidate repair",
        "never applied to the baseline",
    ):
        assert phrase in t.lower(), phrase

    # And all of it is in the committed PDF, each figure read in its own column.
    figure_cols = _columns([n.split()[0] for n, _ in build.KEY_FIGURES], 58, centred=False)
    for (n, caption), col in zip(build.KEY_FIGURES, figure_cols, strict=True):
        assert _flatten(f"{n} {caption}") in col, (n, col)
    timeline_cols = _columns(times, 56, centred=True)
    for (time, label, _), col in zip(build.TIMELINE, timeline_cols, strict=True):
        assert _flatten(f"{time} {label}") in col, (time, col)
    pipeline_cols = _columns([n for n, _, _ in build.PIPELINE], 25, centred=True)
    for (node, label, _), col in zip(build.PIPELINE, pipeline_cols, strict=True):
        assert _flatten(f"{node} {label}") in col, (node, col)
    import pdfplumber

    with pdfplumber.open(PDF) as pdf:
        flat = _flatten(" ".join((p.extract_text() or "") for p in pdf.pages))
    for band in (build.MLFO_BAND, build.SANDBOX_BAND, build.PROPOSAL_NOTE):
        assert _flatten(band) in flat, band


def test_the_report_is_linked_and_the_draft_is_not() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/report/cascadeguard-report.pdf" in readme
    draft = CONCLUSION_DRAFT.stem  # not spelled out: no tracked file may name the draft
    assert draft not in readme and draft not in text()
