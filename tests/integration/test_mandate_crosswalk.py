"""Task 5: docs/institutional-mandate-crosswalk.md is generated from the roles and the loaded
clauses (scripts/mandate_crosswalk.py) and kept current."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def crosswalk() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mandate_crosswalk", ROOT / "scripts" / "mandate_crosswalk.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["mandate_crosswalk"] = module
    spec.loader.exec_module(module)
    return module


def test_the_crosswalk_is_current() -> None:
    text = crosswalk().render()
    committed = (ROOT / "docs" / "institutional-mandate-crosswalk.md").read_text(encoding="utf-8")
    assert committed.replace("\r\n", "\n") == text


def test_six_roles_and_the_adviser_has_no_enforcement_authority() -> None:
    text = crosswalk().render()
    assert text.count("\n## ") == 6
    assert "**The Policy and Legal Adviser has no enforcement authority:**" in text
    adviser = text.split("(`policy_legal_adviser`)", 1)[1]
    assert "Advisory only: no enforcement authority." in adviser
    assert "reviewed clause" not in adviser.split("\n## ", 1)[0]


def test_illustrative_rules_are_never_called_reviewed() -> None:
    for line in crosswalk().render().splitlines():
        if "`illus." in line:
            assert "illustrative rule only (synthetic, not UAE law)" in line, line
            assert "| reviewed clause |" not in line, line
