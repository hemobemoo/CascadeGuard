"""Task 5: docs/standards/ holds the moved Y.3172 and Readiness 2.0 tables and the event's eight
perspectives, with an honest status and existing file paths; no Y.3172 compliance is claimed."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDARDS = ROOT / "docs" / "standards"
PERSPECTIVES = [  # the event page, read 2026-11-06
    "Open data and open-source management",
    "Generative AI content ecosystem",
    "Contextualization of AI solutions and regional development focus",
    "AI integration in domains and cross-domain analysis",
    "Human interaction and supervision in AI",
    "AI policy and implementation opportunity identification",
    "AI for social inclusion",
    "Digital infrastructure and energy considerations",
]


def test_the_eight_perspectives_have_a_status_and_existing_paths() -> None:
    rows = [
        line.split("|")
        for line in (STANDARDS / "event-perspectives.md").read_text(encoding="utf-8").splitlines()
        if re.match(r"^\| \d \|", line)
    ]
    assert [r[2].strip() for r in rows] == PERSPECTIVES
    for r in rows:
        assert r[3].strip() in {"addressed", "partial", "not addressed"}, r[2]
        paths = re.findall(r"`([^`]+)`", r[5])
        assert paths, r[2]
        for path in paths:
            assert (ROOT / path).exists(), path


def test_the_moved_tables_keep_their_rows() -> None:
    y3172 = (STANDARDS / "y3172-mapping.md").read_text(encoding="utf-8")
    readiness = (STANDARDS / "ai-readiness-2.0.md").read_text(encoding="utf-8")
    assert "does not claim compliance with ITU-T Y.3172" in y3172
    assert y3172.count("\n| ") >= 13 and "| P (policy) |" in y3172
    assert readiness.count("\n| ") >= 14 and "| 10 | **AI & Policies** |" in readiness
    pointer = (ROOT / "docs" / "submission-readiness.md").read_text(encoding="utf-8")
    assert "standards/y3172-mapping.md" in pointer and "standards/ai-readiness-2.0.md" in pointer


def test_no_tracked_document_claims_y3172_compliance() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    claim = re.compile(
        r"(?<!not )(?<!no )\b(?:complies with|compliant with|conforms to|certified)\b[^.\n]{0,40}"
        r"Y\.3172|Y\.3172[- ](?:compliant|conformant|certified)",
        re.IGNORECASE,
    )
    found = [p for p in tracked if claim.search((ROOT / p).read_text(encoding="utf-8"))]
    assert found == []
