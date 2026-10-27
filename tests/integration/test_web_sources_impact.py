"""Phase 6c impact check (spec 006c d): the web-transcription drafts change nothing today.

Every run here is compared with a run on a copy of policies/reviewed/ that leaves out every
clause quoted from policies/sources/web/. Drafts are never loaded by the engine, so the baseline,
every role view (and so every LLM cache key), the repair search and the goldens must be
byte-identical. The last test records what would change once the human reviews them.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from cascadeguard import cli
from cascadeguard.agents.cache import cache_key, canonical_view
from cascadeguard.agents.llm import PROMPT_VERSION, response_schema
from cascadeguard.domain.policies import WEB_DIR, ClauseStatus
from cascadeguard.engine.constraints import ANALYSIS
from cascadeguard.engine.repair_search import SearchResult
from cascadeguard.knowledge.loader import REVIEWED_DIR, load_clauses, load_engine_clauses
from cascadeguard.knowledge.retrieval import clauses_for_role
from cascadeguard.simulation.orchestrator import RunResult

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "uae_health_access"
GOLDEN_BASELINE = ROOT / "scenarios" / SCENARIO / "expected_baseline.yaml"
GOLDEN_REPAIRS = ROOT / "scenarios" / SCENARIO / "expected_repairs.yaml"
FAKE_MODEL = "test/model-id-for-cache-keys"  # never sent anywhere; only hashed into the key


def web_ids() -> set[str]:
    return {c.id for c in load_clauses() if (c.source_file or "").startswith(WEB_DIR)}


def copy_reviewed(target: Path, *, drop_web: bool, review_web: bool = False) -> Path:
    """A copy of policies/reviewed/ without the web clauses, or with them set to reviewed."""
    target.mkdir()
    for path in sorted(REVIEWED_DIR.iterdir()):
        if not path.name.endswith(".yaml"):
            continue
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        kept: list[dict[str, Any]] = []
        for clause in data["clauses"]:
            web = str(clause.get("source_file") or "").startswith(WEB_DIR)
            if web and drop_web:
                continue
            if web and review_web:
                clause = {**clause, "status": "reviewed"}
            kept.append(clause)
        (target / path.name).write_text(yaml.safe_dump({"clauses": kept}), encoding="utf-8")
    return target


@pytest.fixture
def without_web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(cli, "REVIEWED_DIR", copy_reviewed(tmp_path / "reviewed", drop_web=True))
    yield


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


def test_only_the_draft_count_line_differs_in_the_cli_output(without_web: None) -> None:
    """The CLI and Markdown export print how many drafts are not loaded; that count is the one
    visible difference (a display line, not part of the baseline result or any golden)."""
    result = cli.run_scenario(SCENARIO)
    fewer = cli.excluded_drafts(result)
    assert cli.format_result(result, fewer + len(web_ids())).replace(
        f"{fewer + len(web_ids())} draft", f"{fewer} draft"
    ) == cli.format_result(result, fewer)


def test_once_reviewed_the_web_clauses_enter_only_the_analysis_roles_views(
    tmp_path: Path,
) -> None:
    """Impact report 4.1: with no normalized reading, a web clause concerns no role or action
    (RuleBook.concerns), so once reviewed it reaches only roles allowed provide_policy_analysis,
    which may cite any loaded clause. Their views, and so their LLM cache keys, would change."""
    reviewed = copy_reviewed(tmp_path / "rev", drop_web=False, review_web=True)
    clauses = load_engine_clauses(reviewed)
    corpus = frozenset(c.id for c in load_clauses(reviewed))
    _, roles = cli.load_scenario(SCENARIO, set(corpus), cli.SCENARIOS_DIR)
    reached = {
        r.id
        for r in roles.roles
        if web_ids() & {c.id for c in clauses_for_role(clauses, corpus, r.id, r.allowed_actions)}
    }
    analysts = {r.id for r in roles.roles if ANALYSIS in r.allowed_actions}
    assert analysts == {"policy_legal_adviser"}
    assert reached == analysts
