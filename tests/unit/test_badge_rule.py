"""The "smallest safe repair" predicate (engine, read-only; human decisions 2026-10-26/27)."""

from dataclasses import replace

import pytest

from cascadeguard.cli import search_repairs
from cascadeguard.engine.repair_search import (
    SMALLEST_SAFE_LABEL,
    TOP_RANKED_LABEL,
    SearchResult,
    is_smallest_safe,
    outcome_text,
)
from cascadeguard.ui import view_model as vm

HEALTH = "health_service_operator"


@pytest.fixture(scope="module")
def found() -> SearchResult:
    return search_repairs("uae_health_access")


def test_rank_one_clean_complete_resolved_without_invalid_output(found: SearchResult) -> None:
    top = found.ranked[0]
    assert top.outcome == "resolved" and not top.invalid_steps and not top.failed_steps
    assert is_smallest_safe(top, 1)
    assert not is_smallest_safe(top, 2)  # only rank 1


def test_partial_conflict_and_incomplete_never_qualify(found: SearchResult) -> None:
    assert not is_smallest_safe(next(c for c in found.ranked if c.outcome == "partial"), 1)
    assert not is_smallest_safe(next(c for c in found.ranked if c.new_conflicts), 1)
    top = found.ranked[0]
    failed = replace(top, replay=replace(top.replay, failed_steps=((0, HEALTH, "x"),)))
    assert not is_smallest_safe(failed, 1)


@pytest.mark.parametrize("run", ["baseline", "replay"])
def test_any_invalid_output_step_blocks_it(found: SearchResult, run: str) -> None:
    top = found.ranked[0]
    result = getattr(top, run)
    flagged = replace(top, **{run: replace(result, invalid_steps=((10, HEALTH),))})
    assert flagged.outcome == "resolved"  # still resolved: only the invalid step decides
    assert not is_smallest_safe(flagged, 1)
    # The display shows "top-ranked repair (resolved)"; the outcome text beside it holds the
    # caveat naming the step.
    assert vm.badge(flagged, 1) == f"{TOP_RANKED_LABEL} (resolved)"
    assert f"{HEALTH} at T+10 ({run})" in outcome_text(flagged)


def test_read_only(found: SearchResult) -> None:
    top = found.ranked[0]
    before = (top.outcome, top.removed, top.masked, top.remaining, outcome_text(top))
    is_smallest_safe(top, 1)
    assert (top.outcome, top.removed, top.masked, top.remaining, outcome_text(top)) == before
    assert vm.SMALLEST_SAFE == SMALLEST_SAFE_LABEL  # the display uses the engine label
