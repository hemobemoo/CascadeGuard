"""Load and validate the clause YAML files in policies/reviewed/.

The engine reads clauses only through `load_engine_clauses`, which admits `reviewed` and
`illustrative` clauses. Drafts are loaded by `load_clauses` so they can be validated and
checked against the extracted PDF text before the human reviews them.
"""

import json
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from cascadeguard.domain.policies import ELISION, ClauseStatus, PolicyClause

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEWED_DIR = PROJECT_ROOT / "policies" / "reviewed"
SOURCES_DIR = PROJECT_ROOT / "policies" / "sources"
EXTRACTED_DIR = PROJECT_ROOT / "policies" / "extracted"

ENGINE_STATUSES = frozenset({ClauseStatus.REVIEWED, ClauseStatus.ILLUSTRATIVE})


class ClauseLoadError(ValueError):
    """A clause file is malformed. The whole load fails; no partial knowledge base."""


def load_clauses(
    directory: Path = REVIEWED_DIR, sources_dir: Path = SOURCES_DIR
) -> list[PolicyClause]:
    """Load every clause of any status, rejecting malformed files and duplicate ids."""
    clauses: list[PolicyClause] = []
    for path in sorted(directory.glob("*.yaml")):
        clauses.extend(_load_file(path, sources_dir))
    seen: set[str] = set()
    for clause in clauses:
        if clause.id in seen:
            raise ClauseLoadError(f"duplicate clause id: {clause.id}")
        seen.add(clause.id)
    return clauses


def load_engine_clauses(
    directory: Path = REVIEWED_DIR, sources_dir: Path = SOURCES_DIR
) -> dict[str, PolicyClause]:
    """Clauses the engine may use: `reviewed` and `illustrative` only, keyed by id."""
    return {c.id: c for c in load_clauses(directory, sources_dir) if c.status in ENGINE_STATUSES}


def quote_found_on_page(clause: PolicyClause, extracted_dir: Path = EXTRACTED_DIR) -> bool:
    """True if the clause text appears verbatim (ignoring whitespace) on its cited page.

    The text may mark an omission with ELISION ("[...]"), e.g. where two-column layouts
    interleave on extraction; every piece must then appear on the page, in order.
    """
    return skipped_texts(clause, extracted_dir) is not None


def skipped_texts(clause: PolicyClause, extracted_dir: Path = EXTRACTED_DIR) -> list[str] | None:
    """The page text each ELISION skips, in order; None if the quote is not on its page."""
    page_text = _page_text(clause, extracted_dir)
    if page_text is None:
        return None
    kept = [i for i, ch in enumerate(page_text) if not ch.isspace()]
    haystack = "".join(page_text[i] for i in kept)
    spans: list[tuple[int, int]] = []
    position = 0
    for piece in clause.text.split(ELISION):
        needle = _squash(piece)
        found = haystack.find(needle, position)
        if found < 0:
            return None
        spans.append((found, found + len(needle)))
        position = found + len(needle)
    return [
        page_text[kept[end] : kept[start - 1] + 1] if start > end else ""
        for (_, end), (start, _) in pairwise(spans)
    ]


def _page_text(clause: PolicyClause, extracted_dir: Path) -> str | None:
    if clause.source_file is None or clause.page is None:
        return None
    jsonl = extracted_dir / f"{Path(clause.source_file).stem}.jsonl"
    if not jsonl.exists():
        return None
    with jsonl.open(encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            if record["page"] == clause.page:
                return str(record["text"])
    return None


def _load_file(path: Path, sources_dir: Path) -> list[PolicyClause]:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ClauseLoadError(f"{path.name}: invalid YAML: {exc}") from exc
    items: Any = cast(dict[str, Any], raw).get("clauses") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ClauseLoadError(f"{path.name}: expected a mapping with a 'clauses' list")
    clauses: list[PolicyClause] = []
    for index, item in enumerate(cast(list[Any], items)):
        try:
            clause = PolicyClause.model_validate(item)
        except ValidationError as exc:
            raise ClauseLoadError(f"{path.name}: clause #{index + 1}: {exc}") from exc
        if clause.source_file is not None and not (sources_dir / clause.source_file).exists():
            raise ClauseLoadError(f"{path.name}: {clause.id}: unknown source_file")
        clauses.append(clause)
    return clauses


def _squash(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())
