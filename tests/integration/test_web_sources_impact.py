"""Phase 6c and 6d impact checks (spec 006c d, spec 006d d): the drafts quoted from the web
transcriptions (6c) and from the three official originals placed in 6d change nothing today.

Every run here is compared with a run on a copy of policies/reviewed/ that leaves out those
clauses. Drafts are never loaded by the engine, so the baseline, every role view (and so every
LLM cache key), the repair search and the goldens must be byte-identical. The "once reviewed"
tests record what would change once the human reviews them.
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
DRAFTS_6D = {
    "unesco.ai-ethics.human-oversight",
    "unesco.ai-ethics.review-and-correct",
    "unesco.ai-ethics.responsibility-accountability",
    "oecd.ai-principles.robustness-override",
    "oecd.ai-principles.accountability-cooperation",
}


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
) -> Path:
    """A copy of policies/reviewed/ without the selected clauses (default: the web ones), or with
    them set to reviewed."""
    target.mkdir()
    for path in sorted(REVIEWED_DIR.iterdir()):
        if not path.name.endswith(".yaml"):
            continue
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        kept: list[dict[str, Any]] = []
        for clause in data["clauses"]:
            chosen = select(clause.get("source_file"))
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


def test_the_web_drafts_exist_and_are_all_drafts() -> None:
    clauses = [c for c in load_clauses() if c.id in web_ids()]
    assert clauses
    assert {c.status for c in clauses} == {ClauseStatus.DRAFT}
    assert all(c.binding is not True and c.normalized is None for c in clauses)
    assert not web_ids() & set(load_engine_clauses())


def test_baseline_views_cache_keys_and_search_are_byte_identical_without_the_web_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_drafts = snapshot()
    monkeypatch.setattr(cli, "REVIEWED_DIR", copy_reviewed(tmp_path / "rev", drop_web=True))
    without_drafts = snapshot()
    assert with_drafts["views"]  # the comparison covers real views and keys
    assert with_drafts["replay_views"]
    assert with_drafts == without_drafts


def test_goldens_still_match_with_the_web_drafts_present() -> None:
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
    monkeypatch.setattr(cli, "REVIEWED_DIR", copy_reviewed(tmp_path / "rev", drop_web=True))
    count, text, md = outputs()
    assert with_count == count + len(web_ids())
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


def test_the_6d_drafts_are_the_re_anchored_clauses_and_all_drafts() -> None:
    clauses = [c for c in load_clauses() if is_6d(c.source_file)]
    assert {c.id for c in clauses} == DRAFTS_6D  # none from the TRA-era cyber strategy
    assert {c.status for c in clauses} == {ClauseStatus.DRAFT}
    assert all(c.binding is False and c.normalized is None for c in clauses)
    assert not DRAFTS_6D & set(load_engine_clauses())


def test_default_path_is_byte_identical_without_the_6d_drafts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default path (no --extracted-context): baseline, every view and LLM cache key, the
    repair search and the replay views are unchanged by the five 6d drafts."""
    with_drafts = snapshot()
    rev = copy_reviewed(tmp_path / "rev", drop_web=True, select=is_6d)
    monkeypatch.setattr(cli, "REVIEWED_DIR", rev)
    assert with_drafts["views"] and with_drafts["replay_views"]
    assert with_drafts == snapshot()


def test_extracted_context_fingerprint_changes_with_the_new_extracted_text(tmp_path: Path) -> None:
    """Expected, not a failure: with --extracted-context on, the prompt version carries a digest
    of the searchable extracted corpus, and the OECD and UNESCO originals add text to it (the
    TRA-era strategy is not searched)."""
    before = tmp_path / "extracted"
    shutil.copytree(EXTRACTED_DIR, before)
    for name in OFFICIAL_6D:
        (before / name.replace(".pdf", ".jsonl")).unlink()
    assert extracted_digest(before) != extracted_digest(EXTRACTED_DIR)
