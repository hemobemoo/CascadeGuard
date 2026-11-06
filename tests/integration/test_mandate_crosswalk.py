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


def rows(role: str) -> dict[str, str]:
    section = crosswalk().render().split(f"(`{role}`)", 1)[1].split("\n## ", 1)[0]
    return {
        line.split("|")[1].strip(" `"): line
        for line in section.splitlines()
        if line.startswith("| `")
    }


def test_authority_is_the_engines_verdict() -> None:
    """Evidence-auditor (Task 5): a conditional permission gives only uncertain authority."""
    determination = rows("health_data_oversight")["issue_determination"]
    assert "uae.fl2-2019.art6" in determination
    assert "uncertain: requires a determination (engine)" in determination
    fallback = rows("health_service_operator")["activate_fallback_channel"]
    assert "uncertain" in fallback and "implied only via `maintain_fallback_plan`" in fallback
    reverse = rows("health_service_operator")["reverse_automated_lockouts"]
    assert "none established (engine)" in reverse


def test_prohibitions_only_where_the_role_can_hold_the_data() -> None:
    share = rows("health_service_operator")["share_incident_status"]
    assert "prohibition on `patient_account_records`" in share and "conditional" in share
    for role in ("telecom_operator", "telecom_regulator"):
        assert "uae.fl2-2019" not in rows(role)["share_incident_status"], role


def test_non_binding_guidance_is_never_a_mandate() -> None:
    review = rows("health_service_operator")["review_automated_lockouts"]
    assert "reviewed guidance only (not binding; no mandate)" in review
