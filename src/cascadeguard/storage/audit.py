"""Audit trail in a local DuckDB file (default data/audit.duckdb, gitignored).

Records every run (baseline or replay) with its event log, findings and diagnosed failures,
plus each repair comparison. Append-only: rows are never updated or deleted.
"""

import json
from pathlib import Path
from typing import Any

import duckdb

from cascadeguard.simulation.orchestrator import RunResult
from cascadeguard.simulation.replay import ReplayComparison

DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "audit.duckdb"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT current_timestamp,
    kind VARCHAR NOT NULL,               -- baseline | replay
    scenario VARCHAR NOT NULL,
    clause_set VARCHAR NOT NULL,
    repair_id VARCHAR,
    summary JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    run_id INTEGER NOT NULL, seq INTEGER NOT NULL, minute INTEGER NOT NULL,
    kind VARCHAR NOT NULL, role VARCHAR, action VARCHAR, target VARCHAR,
    data_category VARCHAR, reasons VARCHAR[], clause_ids VARCHAR[], detail VARCHAR
);
CREATE TABLE IF NOT EXISTS findings (
    run_id INTEGER NOT NULL, minute INTEGER NOT NULL, role VARCHAR, kind VARCHAR NOT NULL,
    clause_ids VARCHAR[], detail VARCHAR
);
CREATE TABLE IF NOT EXISTS failures (
    run_id INTEGER NOT NULL, failure_id VARCHAR NOT NULL, category VARCHAR NOT NULL,
    goals VARCHAR[], roles VARCHAR[], clause_ids VARCHAR[], description VARCHAR,
    qualification VARCHAR
);
CREATE TABLE IF NOT EXISTS comparisons (
    baseline_run_id INTEGER NOT NULL, replay_run_id INTEGER NOT NULL, repair_id VARCHAR NOT NULL,
    requires_authorization BOOLEAN NOT NULL, outcome VARCHAR NOT NULL, summary JSON NOT NULL
);
"""


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


class AuditStore:
    def __init__(self, path: Path = DEFAULT_DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute(_SCHEMA)

    def close(self) -> None:
        self.con.close()

    def record_run(self, result: RunResult, kind: str, repair_id: str | None = None) -> int:
        row = self.con.execute("SELECT coalesce(max(run_id), 0) + 1 FROM runs").fetchone()
        assert row is not None
        run_id = int(row[0])
        self.con.execute(
            "INSERT INTO runs (run_id, kind, scenario, clause_set, repair_id, summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                run_id,
                kind,
                result.scenario_id,
                result.clause_set,
                repair_id,
                _json(result.summary()),
            ],
        )
        self.con.executemany(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [
                    run_id,
                    e.seq,
                    e.minute,
                    e.kind,
                    e.role,
                    e.action,
                    e.target,
                    e.data_category,
                    list(e.reasons),
                    list(e.clause_ids),
                    e.detail,
                ]
                for e in result.log
            ],
        )
        if result.findings:
            self.con.executemany(
                "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?)",
                [
                    [run_id, f.minute, f.role, f.kind, list(f.clause_ids), f.detail]
                    for f in result.findings
                ],
            )
        if result.failures:
            self.con.executemany(
                "INSERT INTO failures VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        run_id,
                        f.id,
                        f.category.value,
                        list(f.goals),
                        list(f.roles),
                        list(f.clause_ids),
                        f.description,
                        f.qualification,
                    ]
                    for f in result.failures
                ],
            )
        return run_id

    def record_comparison(self, comparison: ReplayComparison) -> tuple[int, int]:
        base = self.record_run(comparison.baseline, "baseline")
        rep = self.record_run(comparison.replay, "replay", comparison.proposal.repair_id)
        self.con.execute(
            "INSERT INTO comparisons VALUES (?, ?, ?, ?, ?, ?)",
            [
                base,
                rep,
                comparison.proposal.repair_id,
                comparison.proposal.requires_authorization,
                comparison.outcome,
                _json(comparison.summary()),
            ],
        )
        return base, rep
