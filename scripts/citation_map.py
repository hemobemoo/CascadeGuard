"""Write docs/citation-map.md: which policy documents and clauses the agents cited, from committed
data only (no engine run, no API call). `--check` writes nothing and exits 1 if the committed
file differs from what would be generated.

Sources:
- scripted governed run: scenarios/uae_health_access/scripted_decisions.yaml, with the engine's
  verdicts from docs/evaluation/traces/uae_health_access-baseline.json;
- live governed and live ungoverned runs (gate 4): the decision cache in
  docs/evaluation/gate4/llm_cache/, with the verdicts from docs/evaluation/gate4/baseline.json
  and the ungoverned run in docs/evaluation/gate4/governance-off.json.

    uv run python scripts/citation_map.py [--check]
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from cascadeguard.domain.policies import PolicyClause
from cascadeguard.knowledge.loader import PROJECT_ROOT, load_engine_clauses

SCENARIO_DIR = PROJECT_ROOT / "scenarios" / "uae_health_access"
SCRIPTED_DECISIONS = SCENARIO_DIR / "scripted_decisions.yaml"
SCENARIO_FILE = SCENARIO_DIR / "scenario.yaml"
SCRIPTED_TRACE = PROJECT_ROOT / "docs" / "evaluation" / "traces" / "uae_health_access-baseline.json"
GATE4 = PROJECT_ROOT / "docs" / "evaluation" / "gate4"
LLM_CACHE = GATE4 / "llm_cache"
LIVE_BASELINE = GATE4 / "baseline.json"
LIVE_GOVERNANCE_OFF = GATE4 / "governance-off.json"
OUTPUT = PROJECT_ROOT / "docs" / "citation-map.md"

SCRIPTED = "scripted governed"
LIVE_GOVERNED = "live governed"
LIVE_UNGOVERNED = "live ungoverned"
RUNS = (SCRIPTED, LIVE_GOVERNED, LIVE_UNGOVERNED)

ILLUSTRATIVE_DOC = "Illustrative clauses (scenario only; no source document)"
# Document titles as listed in docs/policy-inventory.md and policies/sources/web/MANIFEST.md.
TITLES = {
    "Federal Decree by Law No. (45) of 2021 Concerning the Protection of Personal Data.pdf": (
        "Federal Decree-Law No. 45 of 2021 (PDPL)"
    ),
    "GDPR-Regulation (EU) 2016-679.pdf": "Regulation (EU) 2016/679 (GDPR), consolidated",
    "Health Data Protection and Confidentiality Policy_EN2022810559.pdf": (
        "Policy for Data and Health Information Protection and Confidentiality "
        "(DHA/HRS/HISHD/PP-11)"
    ),
    "OECD_Recommendation_AI.pdf": (
        "Recommendation of the Council on Artificial Intelligence, OECD/LEGAL/0449"
    ),
    "The UAE Charter for the Development and Use of Artificial Intelligence.pdf": (
        "The UAE Charter for the Development & Use of Artificial Intelligence"
    ),
    "UAE Federal Law No. 2 of 2019. The Use of ICT in Health Fields..pdf": (
        "Federal Law No. 2 of 2019 on ICT in Health Fields (English translation)"
    ),
    "UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf": (
        "UNESCO Recommendation on the Ethics of AI, SHS/BIO/PI/2021/1"
    ),
    "web/01_uae_smart_health_ai_policy.pdf": (
        "National Policy for the Promotion of Smart Health Services and AI in the UAE Health "
        "Sector (web transcription)"
    ),
}


Rejections = dict[tuple[str, int], tuple[list[str], set[str]]]


class CitationMapError(ValueError):
    """The committed data does not join up (unknown clause, unmatched cache entry, ...)."""


@dataclass(frozen=True)
class Citation:
    clause_id: str
    role: str
    minute: int
    run: str
    verdict: str  # "accepted", or "rejected: <reasons>" / "rejected: decision (<reasons>, ...)"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _rejections(export: Any) -> Rejections:
    """(role, minute) -> (reasons, offending clause ids) for each rejected decision."""
    out: Rejections = {}
    for r in export["rejected_decisions"]:
        key = (str(r["role"]), int(r["minute"]))
        if key in out:
            raise CitationMapError(f"two rejected decisions for {key}")
        out[key] = ([str(x) for x in r["reasons"]], {str(c["id"]) for c in r["clauses"]})
    return out


def _verdict(clause_id: str, key: tuple[str, int], rejected: Rejections) -> str:
    if key not in rejected:
        return "accepted"
    reasons, clauses = rejected[key]
    why = ", ".join(reasons)
    if clause_id in clauses:
        return f"rejected: {why}"
    return f"rejected: whole decision ({why} on {', '.join(sorted(clauses))})"


def _unique_ids(citations: Any) -> list[str]:
    """Clause ids in citation order, each once (a decision may cite a clause twice)."""
    ids: list[str] = []
    items: list[Any] = [] if citations is None else list(citations)
    for c in items:
        cid = str(c["clause_id"])
        if cid not in ids:
            ids.append(cid)
    return ids


def scripted_citations() -> list[Citation]:
    data = _read_yaml(SCRIPTED_DECISIONS)
    rejected = _rejections(_read_json(SCRIPTED_TRACE))
    out: list[Citation] = []
    for d in data["decisions"]:
        key = (str(d["role"]), int(d["at_minute"]))
        for cid in _unique_ids(d.get("citations")):
            out.append(Citation(cid, key[0], key[1], SCRIPTED, _verdict(cid, key, rejected)))
    return out


def _actions(items: Any, role: str, minute: int) -> Counter[tuple[str, str | None]]:
    return Counter(
        (str(a["action"]), a.get("target"))
        for a in items
        if a["role"] == role and int(a["minute"]) == minute
    )


def _proposed(decision: Any) -> Counter[tuple[str, str | None]]:
    return Counter((str(a["action_type"]), a.get("target")) for a in decision["proposed_actions"])


Step = tuple[str, int]  # (role, minute)


def live_assignment() -> dict[str, dict[Step, tuple[str, Any]]]:
    """run -> step -> (cache file name, decision). A step with one cache entry was used by both
    live runs; with several, each run's entry is the one whose proposed actions equal that run's
    exported actions for the step."""
    start = datetime.fromisoformat(str(_read_yaml(SCENARIO_FILE)["start_time"]))
    steps: dict[Step, list[tuple[str, Any]]] = defaultdict(list)
    for path in sorted(LLM_CACHE.glob("*.json")):
        entry = _read_json(path)
        if entry["outcome"] != "decision":
            raise CitationMapError(f"{path.name}: outcome {entry['outcome']!r}, not a decision")
        decision = entry["decision"]
        seconds = (datetime.fromisoformat(str(decision["at"])) - start).total_seconds()
        if seconds % 60 or decision["role_id"] != entry["role_id"]:
            raise CitationMapError(f"{path.name}: unexpected time or role")
        steps[(str(entry["role_id"]), int(seconds // 60))].append((path.name, decision))
    governed = _read_json(LIVE_BASELINE)
    ungoverned = _read_json(LIVE_GOVERNANCE_OFF)["ungoverned_run"]
    out: dict[str, dict[Step, tuple[str, Any]]] = {}
    for run, export in ((LIVE_GOVERNED, governed), (LIVE_UNGOVERNED, ungoverned)):
        rejected = _rejections(export)
        out[run] = {}
        for key in sorted(steps):
            entries = steps[key]
            if key in rejected:  # a rejected decision's actions are not exported
                chosen = entries
            else:
                exported = _actions(export["actions"], *key)
                chosen = [e for e in entries if _proposed(e[1]) == exported]
            if len(chosen) != 1:
                raise CitationMapError(f"{run} {key}: {len(chosen)} matching cache entries")
            out[run][key] = chosen[0]
    return out


def shared_live_steps() -> tuple[int, int]:
    """(steps whose cache entry both live runs used, steps in the ungoverned run)."""
    a = live_assignment()
    gov, ungov = a[LIVE_GOVERNED], a[LIVE_UNGOVERNED]
    return sum(1 for k in ungov if gov.get(k, ("",))[0] == ungov[k][0]), len(ungov)


def live_citations() -> list[Citation]:
    out: list[Citation] = []
    exports = {
        LIVE_GOVERNED: _read_json(LIVE_BASELINE),
        LIVE_UNGOVERNED: _read_json(LIVE_GOVERNANCE_OFF)["ungoverned_run"],
    }
    for run, steps in live_assignment().items():
        rejected = _rejections(exports[run])
        for key, (_, decision) in steps.items():
            for cid in _unique_ids(decision["citations"]):
                out.append(Citation(cid, key[0], key[1], run, _verdict(cid, key, rejected)))
    return out


def all_citations() -> list[Citation]:
    return scripted_citations() + live_citations()


def document_counts(
    clauses: dict[str, PolicyClause] | None = None,
) -> dict[str | None, Counter[str]]:
    """Citations per run for each source file with loaded clauses (None = illustrative)."""
    clauses = load_engine_clauses() if clauses is None else clauses
    out: dict[str | None, Counter[str]] = {c.source_file: Counter() for c in clauses.values()}
    for c in all_citations():
        out[clauses[c.clause_id].source_file][c.run] += 1
    return out


def document_binding(source_file: str | None) -> str:
    """The binding cell of table (a) for one source file."""
    clauses = [c for c in load_engine_clauses().values() if c.source_file == source_file]
    return _binding(clauses)


def document_of(clause: PolicyClause) -> str:
    if clause.source_file is None:
        return ILLUSTRATIVE_DOC
    if clause.source_file not in TITLES:
        raise CitationMapError(f"no document title for {clause.source_file!r}")
    return TITLES[clause.source_file]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _binding(clauses: list[PolicyClause]) -> str:
    if all(c.source_file is None for c in clauses):
        return "no (illustrative)"
    names = {True: "binding", False: "not binding", "unknown": "binding unknown"}
    return " / ".join(sorted({names[c.binding] for c in clauses}))


def _minute(m: int) -> str:
    return f"T+{m:02d}"


def build(clauses: dict[str, PolicyClause] | None = None) -> str:
    clauses = load_engine_clauses() if clauses is None else clauses
    citations = all_citations()
    unknown = sorted({c.clause_id for c in citations} - set(clauses))
    if unknown:
        raise CitationMapError(f"cited clause ids not in the loaded clause set: {unknown}")

    by_doc: dict[str, list[PolicyClause]] = defaultdict(list)
    for clause in clauses.values():
        by_doc[document_of(clause)].append(clause)
    by_clause: dict[str, list[Citation]] = defaultdict(list)
    for c in citations:
        by_clause[c.clause_id].append(c)

    def doc_order(doc: str) -> tuple[bool, str]:
        return (doc == ILLUSTRATIVE_DOC, doc)

    shared, ungoverned_steps = shared_live_steps()
    n_runs = Counter(c.run for c in citations)
    rejected = [c for c in citations if c.verdict != "accepted"]
    cited_docs = [d for d in by_doc if any(c.id in by_clause for c in by_doc[d])]
    lines = [
        "# Citation map: policy documents cited by the agents",
        "",
        "_Hypothetical scenario with synthetic data only. Citations are what the agents proposed "
        "and the engine checked; they are not legal conclusions, and no row here says that a "
        "document applies or does not apply._",
        "",
        "Generated by `uv run python scripts/citation_map.py` from committed files only (no "
        "engine run, no API call); `tests/integration/test_citation_map.py` checks that it is "
        "current.",
        "",
        "- **Runs.** _Scripted governed_: the scripted agents "
        "(`scenarios/uae_health_access/scripted_decisions.yaml`), with the engine's verdicts "
        "from `docs/evaluation/traces/uae_health_access-baseline.json`. _Live governed_ and "
        "_live ungoverned_: the gate-4 LLM recording (`docs/evaluation/gate4/llm_cache/`, "
        "verdicts from `baseline.json` and `governance-off.json` there). The ungoverned run "
        f"reused {shared} of its {ungoverned_steps} decisions from the governed run, so those "
        "citations are counted in both live runs.",
        "- **Counted once per decision.** A clause cited twice in one decision counts once.",
        "- **Accepted** means the engine accepted the decision's citations (every cited clause "
        "loaded and in scope); each proposed action is still judged on its own. **Rejected** "
        "means the engine rejected the whole decision and recorded a finding; the clause that "
        "caused it is marked with the reason, the other clauses in that decision with "
        "'whole decision'.",
        "- **Status label** as shown by the engine and UI: `reviewed` = checked by the human "
        "against the source; `(interpreted)` = the machine-readable reading is an "
        "interpretation; `illustrative` = scenario-only, not from any source.",
        "- **Binding** describes the instrument in its own jurisdiction, not whether it applies "
        "to this scenario; each clause's scope and applicability notes are in its YAML file in "
        "`policies/reviewed/`.",
        "",
        f"Totals: {len(citations)} citations ({n_runs[SCRIPTED]} scripted governed, "
        f"{n_runs[LIVE_GOVERNED]} live governed, {n_runs[LIVE_UNGOVERNED]} live ungoverned), "
        f"{len(rejected)} in rejected decisions; {len(by_clause)} of {len(clauses)} loaded "
        f"clauses cited, from {len(cited_docs)} of {len(by_doc)} document groups.",
        "",
        "## (a) By document",
        "",
        "| Document | Source file | Issuer | Binding | Clauses loaded | Clauses cited | Cited by "
        "(roles) | Scripted governed | Live governed | Live ungoverned |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for doc in sorted(by_doc, key=doc_order):
        members = by_doc[doc]
        cites = [c for m in members for c in by_clause.get(m.id, [])]
        counts = Counter(c.run for c in cites)
        issuers = sorted({m.issuer for m in members})
        source = members[0].source_file
        roles = ", ".join(sorted({c.role for c in cites})) or "—"
        lines.append(
            f"| {_cell(doc)} | {f'`{source}`' if source else '—'} | {_cell('; '.join(issuers))} "
            f"| {_binding(members)} | {len(members)} | "
            f"{sum(1 for m in members if m.id in by_clause)} | {roles} | "
            + " | ".join(str(counts[r]) for r in RUNS)
            + " |"
        )
    lines += [
        "",
        "## (b) By clause",
        "",
        "Cited clauses only; the loaded clauses no agent cited are listed after the table.",
        "",
        "| Clause | Document | Page / article | Status label | Cited by (role @ minute, run) "
        "| Accepted / rejected |",
        "|---|---|---|---|---|---|",
    ]
    for doc in sorted(by_doc, key=doc_order):
        for clause in sorted(by_doc[doc], key=lambda c: c.id):
            cites = by_clause.get(clause.id)
            if not cites:
                continue
            grouped: dict[tuple[int, str, str], list[str]] = defaultdict(list)
            for c in cites:
                grouped[(c.minute, c.role, c.verdict)].append(c.run)
            who = "<br>".join(
                f"{role} @ {_minute(m)} ({', '.join(sorted(runs, key=RUNS.index))})"
                + ("" if verdict == "accepted" else f": **{verdict}**")
                for (m, role, verdict), runs in sorted(grouped.items())
            )
            verdicts = Counter("accepted" if c.verdict == "accepted" else "rejected" for c in cites)
            tally = f"{verdicts['accepted']} accepted"
            if verdicts["rejected"]:
                tally += f", {verdicts['rejected']} rejected"
            where = (
                "—"
                if clause.page is None
                else f"p. {clause.page}" + (f", {clause.article}" if clause.article else "")
            )
            lines.append(
                f"| `{clause.id}` | {_cell(doc)} | {_cell(where)} | {clause.status_label} | "
                f"{who} | {tally} |"
            )
    uncited = sorted(c for c in clauses if c not in by_clause)
    lines += [
        "",
        "Loaded but not cited by any agent: "
        + (", ".join(f"`{c}`" for c in uncited) if uncited else "none")
        + ".",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None, output: Path = OUTPUT) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare only; write nothing")
    args = parser.parse_args(argv)
    text = build()
    old = output.read_text(encoding="utf-8").replace("\r\n", "\n") if output.exists() else None
    shown = output.as_posix()
    if output.is_relative_to(PROJECT_ROOT):
        shown = output.relative_to(PROJECT_ROOT).as_posix()
    if old == text:
        return 0
    if args.check:
        print(f"stale: {shown}")
        return 1
    output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
