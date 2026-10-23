"""CLI output: identical across fresh processes and hash seeds; every clause id carries a label."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = "tests/fixtures/clauses"
CLAUSE_ID = re.compile(r"\b(?:illus|uae|dha|itu|mocai|nist|eu|oecd)\.[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def run_cli(seed: str, *extra: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(
        [sys.executable, "-m", "cascadeguard.cli", "run", "uae_health_access", *extra],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return done.stdout


@pytest.mark.parametrize("extra", [(), ("--clauses", FIXTURES)])
def test_output_is_identical_across_fresh_processes_and_hash_seeds(extra: tuple[str, ...]) -> None:
    outputs = {run_cli(seed, *extra) for seed in ("0", "1", "12345")}
    assert len(outputs) == 1


@pytest.mark.parametrize("extra", [(), ("--clauses", FIXTURES)])
def test_every_clause_id_is_shown_with_its_status_label(extra: tuple[str, ...]) -> None:
    """Each clause id must appear as "<id> [<label>]" on its own line or the next one
    (a failure description is followed by its labelled "clauses:" line)."""
    lines = run_cli("0", *extra).splitlines()
    assert any(CLAUSE_ID.search(line) for line in lines)
    for i, line in enumerate(lines):
        nearby = line + "\n" + (lines[i + 1] if i + 1 < len(lines) else "")
        for clause_id in set(CLAUSE_ID.findall(line)):
            assert f"{clause_id} [" in nearby, line
