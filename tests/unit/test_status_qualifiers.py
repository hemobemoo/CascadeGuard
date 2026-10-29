"""Status labels carry binding status and source type (human decisions 2026-10-29): agents, the
CLI and the UI see e.g. "reviewed · not binding · foreign precedent" next to a clause, never a
bare "reviewed" for non-binding, foreign, translated or unverified material."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from cascadeguard.cli import load_world
from cascadeguard.domain.policies import (
    LABEL_SEPARATOR,
    OCR_FLAG,
    SOURCE_TYPES,
    TRANSLATIONS,
    WEB_FLAG,
    ClauseStatus,
    PolicyClause,
    in_source_dir,
)
from cascadeguard.knowledge.loader import load_clauses
from cascadeguard.ui import view_model as vm

ROOT = Path(__file__).resolve().parents[2]
BASE: dict[str, Any] = {
    "id": "test.clause",
    "title": "A clause",
    "text": "Some verbatim text.",
    "source_file": "doc.pdf",
    "page": 3,
    "issuer": "Issuer",
    "jurisdiction": "UAE",
    "document_date": "2021",
    "status": "reviewed",
    "binding": True,
}
BINDING = {True: "binding", False: "not binding", "unknown": "binding unknown"}


@pytest.mark.parametrize(
    ("changes", "label"),
    [
        ({}, "reviewed · binding"),
        ({"binding": False}, "reviewed · not binding"),
        ({"binding": "unknown", "jurisdiction": "Dubai, UAE"}, "reviewed · binding unknown"),
        ({"binding": False, "jurisdiction": "EU"}, "reviewed · not binding · foreign precedent"),
        (
            {"binding": False, "jurisdiction": "United States (voluntary framework)"},
            "reviewed · not binding · foreign precedent",
        ),
        (
            {"binding": False, "jurisdiction": "International (ITU-T Recommendation)"},
            "reviewed · not binding · international precedent",
        ),
        (  # whole word, any case
            {"binding": False, "jurisdiction": "international (x)"},
            "reviewed · not binding · international precedent",
        ),
        (
            {"binding": False, "jurisdiction": "Internationale Org"},
            "reviewed · not binding · foreign precedent",
        ),
        (  # names the UAE, but is not a UAE jurisdiction
            {"binding": False, "jurisdiction": "International (UAE adherence not checked)"},
            "reviewed · not binding · international precedent",
        ),
        (
            {"binding": "unknown", "source_file": "web/01_page.pdf", "notes": WEB_FLAG},
            "reviewed · binding unknown · web transcription",
        ),
        (
            {"source_file": "ocr/doc.ocr.pdf", "notes": OCR_FLAG, "status": "draft"},
            "draft · binding · OCR copy",
        ),
        (  # a web copy of a foreign source keeps both qualifiers
            {
                "binding": False,
                "jurisdiction": "International",
                "source_file": "web/06_page.pdf",
                "notes": WEB_FLAG,
            },
            "reviewed · not binding · web transcription · international precedent",
        ),
        ({"jurisdiction": "United Arab Emirates"}, "reviewed · binding"),
        ({"jurisdiction": "UAE (federal)"}, "reviewed · binding"),
        (
            {"binding": False, "jurisdiction": "UAEU partner states"},
            "reviewed · not binding · foreign precedent",
        ),
        (
            {"binding": False, "jurisdiction": "Dubaian Republic"},
            "reviewed · not binding · foreign precedent",
        ),
        (
            {"binding": False, "source_file": "UAE Policy Foundation.pdf"},
            "reviewed · not binding · unofficial compilation",
        ),
        (  # other spellings the loader accepts keep the qualifier
            {"binding": False, "source_file": "./uae policy foundation.PDF"},
            "reviewed · not binding · unofficial compilation",
        ),
        (
            {"source_file": "Dubai Law No. (26) of 2015.pdf", "jurisdiction": "Dubai, UAE"},
            "reviewed · binding · English translation",
        ),
        (
            {"source_file": "./dubai law no. (26) of 2015.PDF", "status": "draft"},
            "draft · binding · English translation",
        ),
        (  # an OCR copy of a translation keeps both qualifiers
            {
                "source_file": "ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf",
                "notes": OCR_FLAG,
                "status": "draft",
            },
            "draft · binding · OCR copy · English translation",
        ),
        (  # an issuer's own English version (Arabic prevails) is not listed as a translation
            {"source_file": "Health Data Protection and Confidentiality Policy_EN2022810559.pdf"},
            "reviewed · binding",
        ),
        (
            {
                "status": "illustrative",
                "binding": False,
                "source_file": None,
                "page": None,
                "notes": "needed by the scenario",
            },
            "illustrative",
        ),
    ],
)
def test_label_shows_binding_status_and_source_type(changes: dict[str, Any], label: str) -> None:
    assert PolicyClause.model_validate(BASE | changes).status_label == label


# Every UAE source that is an English translation not verified as official, listed by hand.
TRANSLATED_IN_CORPUS = {
    "887026278-TDRA-Telecom-Law-Final-English-o.pdf",
    "ocr/887026278-TDRA-Telecom-Law-Final-English-o.ocr.pdf",
    "Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf",
    "UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf",
}
# Every UAE jurisdiction in the corpus, listed by hand (independent of is_uae_jurisdiction).
# A clause with a new jurisdiction fails here until it is added to one of these sets.
UAE_IN_CORPUS = {
    "UAE",
    "Dubai, UAE",
    "UAE (federal public policy, health sector)",
    "UAE (illustrative)",
    "UAE (national strategy)",
}
FOREIGN_IN_CORPUS = {"EU", "United States (voluntary framework)"}
INTERNATIONAL_IN_CORPUS = {
    "International (ITU-T Recommendation)",
    "International (OECD Adherents; non-binding recommendation; UAE adherence not checked)",
    "International (OECD paper)",
    "International (UNESCO Member States; non-binding recommendation)",
}


def test_every_repository_clause_label_states_binding_and_source_type() -> None:
    for c in load_clauses():
        parts = c.status_label.split(LABEL_SEPARATOR)
        if c.status is ClauseStatus.ILLUSTRATIVE:
            assert parts == [c.status_label], c.id
            continue
        assert parts[1] == BINDING[c.binding], c.id
        known = UAE_IN_CORPUS | FOREIGN_IN_CORPUS | INTERNATIONAL_IN_CORPUS
        assert c.jurisdiction in known, c.jurisdiction
        expected: list[str] = []
        if in_source_dir(c.source_file, "web/"):
            expected.append("web transcription")
        elif in_source_dir(c.source_file, "ocr/"):
            expected.append("OCR copy")
        elif c.source_file == "UAE Policy Foundation.pdf":
            expected.append("unofficial compilation")
        if c.source_file in TRANSLATED_IN_CORPUS:
            expected.append("English translation")
        if c.jurisdiction in FOREIGN_IN_CORPUS:
            expected.append("foreign precedent")
        elif c.jurisdiction in INTERNATIONAL_IN_CORPUS:
            expected.append("international precedent")
        assert parts[2:] == expected, c.id


TRANSLATIONS_HEADING = "**English translations not verified as official**"


def test_every_recorded_source_type_matches_the_inventory() -> None:
    """SOURCE_TYPES must say what docs/policy-inventory.md says about each source."""
    inventory = (ROOT / "docs" / "policy-inventory.md").read_text(encoding="utf-8")
    rows = {
        line.split("|")[2].strip(" `"): line for line in inventory.splitlines() if "| `" in line
    }
    for source, kind in SOURCE_TYPES.items():
        assert kind.casefold() in rows[source].casefold(), source
    section = inventory.split(TRANSLATIONS_HEADING, 1)[1].split("\n\n", 2)[1]
    listed = {line.strip("- `") for line in section.splitlines()}
    assert listed == set(TRANSLATIONS)


SHOWN = {
    "eu.gdpr.art33-1": "reviewed · not binding · foreign precedent",
    "unesco.ai-ethics.review-and-correct": "reviewed · not binding · international precedent",
    "oecd.ai-principles.robustness-override": "reviewed · not binding · international precedent",
    "uae.mohap-smart-health.p7-liability": "reviewed · binding unknown · web transcription",
    "uae.fl2-2019.art2": "reviewed · binding · English translation",
}


def test_agents_the_cli_and_the_ui_see_the_qualified_labels() -> None:
    world = load_world("uae_health_access")
    baseline = world.baseline()
    adviser = next(v for v in baseline.views if v.role_id == "policy_legal_adviser")
    in_view = {c.id: c.status_label for c in adviser.role_clauses}
    ui = vm.role_view(
        baseline, "policy_legal_adviser", adviser.minute, world.roles.known_categories()
    )
    cli = subprocess.run(
        [sys.executable, "-m", "cascadeguard.cli", "run", "uae_health_access"],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    for cid, label in SHOWN.items():
        assert in_view[cid] == label, cid
        assert any(line.startswith(f"{cid} [{label}]") for line in ui.role_clauses), cid
        assert f"- {cid} [{label}]" in cli, cid
