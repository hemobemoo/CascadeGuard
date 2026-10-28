"""Phase 6c and 6d impact checks (spec 006c d, spec 006d d), as rewritten after gate 1
(human, 2026-10-28). The web part was approved in advance (Phase 6c decision 6); the 6d part
follows from the gate-1 decision itself.

Every run here is compared with a run on a copy of policies/reviewed/ that leaves out some of
the web (6c) or 6d clauses. The ones still draft are never loaded, so leaving them out changes
nothing. The ones the human reviewed carry no normalized reading, so they reach only
`policy_legal_adviser`: leaving them out changes that role's views (and LLM cache keys) and
nothing else, and the repair search stays byte-identical. The baseline changes only through
`eu.gdpr.art33-1` (not a web or 6d clause), which the baseline golden records.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from cascadeguard import cli
from cascadeguard.agents.cache import cache_key, canonical_view
from cascadeguard.agents.llm import PROMPT_VERSION, response_schema
from cascadeguard.domain.policies import WEB_DIR, ClauseStatus, in_source_dir
from cascadeguard.engine.constraints import ANALYSIS
from cascadeguard.engine.repair_search import SearchResult
from cascadeguard.knowledge.loader import (
    EXTRACTED_DIR,
    REVIEWED_DIR,
    load_clauses,
    load_engine_clauses,
)
from cascadeguard.knowledge.retrieval import clauses_for_role, extracted_digest
from cascadeguard.simulation.orchestrator import RunResult

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "uae_health_access"
GOLDEN_BASELINE = ROOT / "scenarios" / SCENARIO / "expected_baseline.yaml"
GOLDEN_REPAIRS = ROOT / "scenarios" / SCENARIO / "expected_repairs.yaml"
FAKE_MODEL = "test/model-id-for-cache-keys"  # never sent anywhere; only hashed into the key
# The three official originals placed in Phase 6d.
OFFICIAL_6D = frozenset(
    {
        "OECD_Recommendation_AI.pdf",
        "UNESCO Recommendation on the Ethics of Artificial Intelligence.pdf",
        "UAE_National_Cybersecurity_Strategy.pdf",
    }
)
CLAUSES_6D = {
    "unesco.ai-ethics.human-oversight",
    "unesco.ai-ethics.review-and-correct",
    "unesco.ai-ethics.responsibility-accountability",
    "oecd.ai-principles.robustness-override",
    "oecd.ai-principles.accountability-cooperation",
}
# Gate 1 (Ibrahim Melhem, 2026-10-28): the web clauses the human reviewed. All 6d clauses were.
REVIEWED_WEB = {"uae.mohap-smart-health.p7-liability"}
ANALYST = "policy_legal_adviser"


def is_web(source_file: str | None) -> bool:
    return in_source_dir(source_file, WEB_DIR)


def is_6d(source_file: str | None) -> bool:
    return source_file in OFFICIAL_6D


def ids_from(select: Callable[[str | None], bool]) -> set[str]:
    return {c.id for c in load_clauses() if select(c.source_file)}


def web_ids() -> set[str]:
    return ids_from(is_web)


def copy_reviewed(
    target: Path,
    *,
    drop_web: bool,
    review_web: bool = False,
    select: Callable[[str | None], bool] = is_web,
    status: str | None = None,
) -> Path:
    """A copy of policies/reviewed/ without the selected clauses (default: the web ones), or with
    them set to reviewed. `status` narrows the selection to clauses with that status."""
    target.mkdir()
    for path in sorted(REVIEWED_DIR.iterdir()):
        if not path.name.endswith(".yaml"):
            continue
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        kept: list[dict[str, Any]] = []
        for clause in data["clauses"]:
            chosen = select(clause.get("source_file")) and status in (None, clause["status"])
            if chosen and drop_web:
                continue
            if chosen and review_web:
                clause = {**clause, "status": "reviewed"}
            kept.append(clause)
        (target / path.name).write_text(yaml.safe_dump({"clauses": kept}), encoding="utf-8")
    return target


def dump(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def views_and_keys(result: RunResult) -> list[tuple[bytes, str]]:
    schema = response_schema()
    return [
        (dump(canonical_view(v)), cache_key(v.role_id, v, PROMPT_VERSION, FAKE_MODEL, schema))
        for v in result.views
    ]


def snapshot() -> dict[str, Any]:
    baseline = cli.run_scenario(SCENARIO)
    found: SearchResult = cli.search_repairs(SCENARIO)
    replays = (*found.ranked, *found.inconclusive)
    return {
        "baseline": dump(baseline.summary()),
        "loaded": baseline.loaded_clauses,
        "views": views_and_keys(baseline),
        "search": dump(found.summary()),
        "replay_views": [views_and_keys(c.replay) for c in replays],
    }


def test_web_clause_statuses_follow_the_gate_1_decisions() -> None:
    clauses = [c for c in load_clauses() if c.id in web_ids()]
    assert {c.id for c in clauses if c.status is ClauseStatus.REVIEWED} == REVIEWED_WEB
    assert {c.status for c in clauses if c.id not in REVIEWED_WEB} == {ClauseStatus.DRAFT}
    assert all(c.binding is not True and c.normalized is None for c in clauses)
    assert web_ids() & set(load_engine_clauses()) == REVIEWED_WEB


def test_baseline_views_cache_keys_and_search_are_byte_identical_without_the_web_drafts_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_drafts = snapshot()
    rev = copy_reviewed(tmp_path / "rev", drop_web=True, status="draft")
    monkeypatch.setattr(cli, "REVIEWED_DIR", rev)
    without_drafts = snapshot()
    assert with_drafts["views"]  # the comparison covers real views and keys
    assert with_drafts["replay_views"]
    assert with_drafts == without_drafts


def test_goldens_match_with_the_remaining_web_drafts_present() -> None:
    assert web_ids()
    assert cli.run_scenario(SCENARIO).summary() == yaml.safe_load(
        GOLDEN_BASELINE.read_text(encoding="utf-8")
    )
    golden = yaml.safe_load(GOLDEN_REPAIRS.read_text(encoding="utf-8"))
    assert cli.search_repairs(SCENARIO).summary() == golden["search"]


def test_only_the_draft_count_line_differs_in_the_cli_and_markdown_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI and Markdown export print how many drafts are not loaded; that count is the one
    visible difference (a display line, not part of the baseline result or any golden)."""

    def outputs() -> tuple[int, str, str]:
        result = cli.run_scenario(SCENARIO)
        drafts = cli.excluded_drafts(result)
        markdown = cli.baseline_markdown(SCENARIO, result, drafts)
        return drafts, cli.format_result(result, drafts), markdown

    with_count, with_text, with_md = outputs()
    rev = copy_reviewed(tmp_path / "rev", drop_web=True, status="draft")
    monkeypatch.setattr(cli, "REVIEWED_DIR", rev)
    count, text, md = outputs()
    assert with_count == count + len(web_ids() - REVIEWED_WEB)
    assert with_text != text and with_md != md  # the count line is printed
    line = f"{with_count} draft clauses not loaded"
    fewer = f"{count} draft clauses not loaded"
    assert with_text.replace(line, fewer) == text
    assert with_md.replace(line, fewer) == md


@pytest.mark.parametrize("select", [is_web, is_6d], ids=["6c-web", "6d-official"])
def test_once_reviewed_the_new_clauses_enter_only_the_analysis_roles_views(
    tmp_path: Path, select: Callable[[str | None], bool]
) -> None:
    """Impact report 4.1: with no normalized reading, a web clause concerns no role or action
    (RuleBook.concerns), so once reviewed it reaches only roles allowed provide_policy_analysis,
    which may cite any loaded clause. Their views, and so their LLM cache keys, would change."""
    reviewed = copy_reviewed(tmp_path / "rev", drop_web=False, review_web=True, select=select)
    clauses = load_engine_clauses(reviewed)
    corpus = frozenset(c.id for c in load_clauses(reviewed))
    _, roles = cli.load_scenario(SCENARIO, set(corpus), cli.SCENARIOS_DIR)
    reached = {
        r.id
        for r in roles.roles
        if ids_from(select)
        & {c.id for c in clauses_for_role(clauses, corpus, r.id, r.allowed_actions)}
    }
    analysts = {r.id for r in roles.roles if ANALYSIS in r.allowed_actions}
    assert analysts == {"policy_legal_adviser"}
    assert reached == analysts


# --- Phase 6d (spec 006d d) ----------------------------------------------------------------


def test_the_6d_clauses_are_the_re_anchored_ones_and_all_reviewed() -> None:
    clauses = [c for c in load_clauses() if is_6d(c.source_file)]
    assert {c.id for c in clauses} == CLAUSES_6D  # none from the TRA-era cyber strategy
    assert {c.status for c in clauses} == {ClauseStatus.REVIEWED}
    assert all(c.binding is False and c.normalized is None for c in clauses)
    assert set(load_engine_clauses()) >= CLAUSES_6D


def role_of(view: tuple[bytes, str]) -> str:
    return json.loads(view[0])["role_id"]


@pytest.mark.parametrize("select", [is_web, is_6d], ids=["6c-web", "6d-official"])
def test_reviewed_clauses_change_only_the_analysts_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, select: Callable[[str | None], bool]
) -> None:
    """Default path (no --extracted-context): leaving out the reviewed web or 6d clauses changes
    `policy_legal_adviser`'s views (and cache keys) only; the baseline, the repair search, every
    other role's views and the number of replays are byte-identical."""
    with_reviewed = snapshot()
    rev = copy_reviewed(tmp_path / "rev", drop_web=True, select=select, status="reviewed")
    monkeypatch.setattr(cli, "REVIEWED_DIR", rev)
    without = snapshot()
    assert with_reviewed["baseline"] == without["baseline"]
    assert with_reviewed["search"] == without["search"]
    pairs = list(zip(with_reviewed["views"], without["views"], strict=True))
    for replay, other in zip(with_reviewed["replay_views"], without["replay_views"], strict=True):
        pairs += list(zip(replay, other, strict=True))
    assert {role_of(a) for a, b in pairs if a != b} == {ANALYST}
    assert all(role_of(a) == role_of(b) for a, b in pairs)


# Gate 1 (2026-10-28): the two reviewed clauses that are neither web nor 6d.
OTHER_REVIEWED = {"dha.pp11.applicability", "eu.gdpr.art33-1"}


def test_the_other_gate_1_clauses_change_only_the_analysts_views(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back to draft on a copy, `dha.pp11.applicability` and `eu.gdpr.art33-1` change only
    `policy_legal_adviser`'s views; the repair search is byte-identical. The baseline changes
    through eu.gdpr.art33-1 (its golden records the reviewed run)."""
    reviewed = snapshot()
    rev = tmp_path / "rev"
    rev.mkdir()
    for path in sorted(REVIEWED_DIR.glob("*.yaml")):
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["clauses"] = [
            {**c, "status": "draft"} if c["id"] in OTHER_REVIEWED else c for c in data["clauses"]
        ]
        (rev / path.name).write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setattr(cli, "REVIEWED_DIR", rev)
    drafted = snapshot()
    assert reviewed["search"] == drafted["search"]
    pairs = list(zip(reviewed["views"], drafted["views"], strict=True))
    for replay, other in zip(reviewed["replay_views"], drafted["replay_views"], strict=True):
        pairs += list(zip(replay, other, strict=True))
    assert {role_of(a) for a, b in pairs if a != b} == {ANALYST}
    assert all(role_of(a) == role_of(b) for a, b in pairs)


def test_extracted_context_fingerprint_changes_with_the_new_extracted_text(tmp_path: Path) -> None:
    """Expected, not a failure: with --extracted-context on, the prompt version carries a digest
    of the searchable extracted corpus, and the OECD and UNESCO originals add text to it (the
    TRA-era strategy is not searched)."""
    before = tmp_path / "extracted"
    shutil.copytree(EXTRACTED_DIR, before)
    for name in OFFICIAL_6D:
        (before / name.replace(".pdf", ".jsonl")).unlink()
    assert extracted_digest(before) != extracted_digest(EXTRACTED_DIR)
