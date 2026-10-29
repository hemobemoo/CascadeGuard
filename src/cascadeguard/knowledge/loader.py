"""Load and validate the clause YAML files in policies/reviewed/.

The engine reads clauses only through `load_engine_clauses`, which admits `reviewed` and
`illustrative` clauses. Drafts are loaded by `load_clauses` so they can be validated and
checked against the extracted PDF text before the human reviews them.
"""

import hashlib
import json
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from cascadeguard.domain.policies import ELISION, TRANSCRIBED_FLAG, ClauseStatus, PolicyClause

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVIEWED_DIR = PROJECT_ROOT / "policies" / "reviewed"
SOURCES_DIR = PROJECT_ROOT / "policies" / "sources"
EXTRACTED_DIR = PROJECT_ROOT / "policies" / "extracted"
# Page-image transcriptions for sources whose text layer is unreliable (see TRANSCRIBED_FLAG).
TRANSCRIPTIONS_DIR = PROJECT_ROOT / "policies" / "transcriptions"
APPROVALS_FILE = PROJECT_ROOT / "policies" / "approvals.yaml"

ENGINE_STATUSES = frozenset({ClauseStatus.REVIEWED, ClauseStatus.ILLUSTRATIVE})
# The two published books are context only and never a clause source (AGENTS.md).
# Compared case-insensitively: Windows and macOS file systems ignore case.
BOOK_MARKERS = ("abhivardhan", "oxford handbook")
ALLOWED_NON_CLAUSE_FILES = frozenset({"readme.md"})


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of keeping the last one."""


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    keys: list[Any] = [loader.construct_object(k) for k, _ in node.value]  # pyright: ignore[reportUnknownMemberType]
    duplicates = sorted({str(k) for k in keys if keys.count(k) > 1})
    if duplicates:
        raise yaml.constructor.ConstructorError(
            None, None, f"duplicate keys {duplicates}", node.start_mark
        )
    return dict(loader.construct_pairs(node))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _no_duplicate_keys,  # pyright: ignore[reportArgumentType]
)


class ClauseLoadError(ValueError):
    """A clause file is malformed. The whole load fails; no partial knowledge base."""


def load_clauses(
    directory: Path = REVIEWED_DIR, sources_dir: Path = SOURCES_DIR
) -> list[PolicyClause]:
    """Load every clause of any status, rejecting malformed files and duplicate ids."""
    entries = sorted(directory.iterdir())
    strays = sorted(
        p.name
        for p in entries
        if p.is_dir()
        or (not p.name.endswith(".yaml") and p.name.casefold() not in ALLOWED_NON_CLAUSE_FILES)
    )
    if strays:
        raise ClauseLoadError(f"only lowercase .yaml clause files are allowed here, found {strays}")
    clauses: list[PolicyClause] = []
    for path in (p for p in entries if p.name.endswith(".yaml")):
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


def clause_digest(clause: PolicyClause) -> str:
    """SHA-256 of every field except `status`: any edit to a clause changes its digest."""
    content = clause.model_dump(mode="json", exclude={"status"})
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


APPROVAL_KEYS = frozenset({"approved", "reapproval_needed", "approved_transcriptions"})


def _approvals_data(path: Path) -> dict[str, Any]:
    raw: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(raw, dict) or frozenset(cast(dict[str, Any], raw)) != APPROVAL_KEYS:
        raise ClauseLoadError(f"{path.name}: expected exactly {sorted(APPROVAL_KEYS)}")
    return cast(dict[str, Any], raw)


def load_approvals(path: Path = APPROVALS_FILE) -> tuple[dict[str, str], tuple[str, ...]]:
    """The human's approved digests and the clauses awaiting re-approval (approvals.yaml)."""
    data = _approvals_data(path)
    approved = cast(dict[str, str], data["approved"] or {})
    pending = cast(list[str], data["reapproval_needed"] or [])
    return dict(approved), tuple(pending)


def load_transcription_approvals(path: Path = APPROVALS_FILE) -> dict[str, str]:
    """The human's approved page-image transcriptions: "<source_file>#<page>" -> the SHA-256 of
    the page text at approval (approvals.yaml, `approved_transcriptions`)."""
    return dict(cast(dict[str, str], _approvals_data(path)["approved_transcriptions"] or {}))


def transcription_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quote_found_on_page(
    clause: PolicyClause,
    extracted_dir: Path = EXTRACTED_DIR,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
) -> bool:
    """True if the clause text appears verbatim (ignoring whitespace) on its cited page: in the
    page-image transcription for a clause flagged TRANSCRIBED_FLAG, else in the extracted text.

    The text may mark an omission with ELISION ("[...]"), e.g. where two-column layouts
    interleave on extraction; every piece must then appear on the page, in order.
    """
    return skipped_texts(clause, extracted_dir, transcriptions_dir) is not None


def skipped_texts(
    clause: PolicyClause,
    extracted_dir: Path = EXTRACTED_DIR,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
) -> list[str] | None:
    """The page text each ELISION skips, in order; None if the quote is not on its page."""
    if TRANSCRIBED_FLAG in (clause.notes or ""):
        page_text = _page_text(clause, transcriptions_dir, transcribed=True)
    else:
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


def _page_text(clause: PolicyClause, directory: Path, transcribed: bool = False) -> str | None:
    """The cited page's text. A transcription record must say "transcribed": true, and an
    extracted record must not, so neither stands in for the other. Two records for the page are
    refused: an unchecked one could otherwise shadow the one the human approved."""
    if clause.source_file is None or clause.page is None:
        return None
    jsonl = directory / f"{Path(clause.source_file).stem}.jsonl"
    if not jsonl.exists():
        return None
    texts: list[str] = []
    with jsonl.open(encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            # Same stem, other document (an original and a web or OCR copy): never a match.
            if (
                record["page"] == clause.page
                and record["source_file"] == clause.source_file
                and (record.get("transcribed") is True) == transcribed
            ):
                texts.append(str(record["text"]))
    if len(texts) > 1:
        raise ClauseLoadError(f"{jsonl.name}: {len(texts)} records for page {clause.page}")
    return texts[0] if texts else None


def _load_file(path: Path, sources_dir: Path) -> list[PolicyClause]:
    try:
        raw: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:  # includes duplicate keys
        raise ClauseLoadError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict) or set(cast(dict[str, Any], raw)) != {"clauses"}:
        raise ClauseLoadError(f"{path.name}: expected a mapping with only a 'clauses' list")
    items: Any = cast(dict[str, Any], raw)["clauses"]
    if not isinstance(items, list):
        raise ClauseLoadError(f"{path.name}: expected a mapping with a 'clauses' list")
    clauses: list[PolicyClause] = []
    for index, item in enumerate(cast(list[Any], items)):
        try:
            clause = PolicyClause.model_validate(item)
        except ValidationError as exc:
            raise ClauseLoadError(f"{path.name}: clause #{index + 1}: {exc}") from exc
        if clause.source_file is not None:
            _check_source(path.name, clause.id, clause.source_file, sources_dir)
        clauses.append(clause)
    return clauses


def _check_source(file_name: str, clause_id: str, source_file: str, sources_dir: Path) -> None:
    where = f"{file_name}: {clause_id}"
    if any(b in source_file.casefold() for b in BOOK_MARKERS):
        raise ClauseLoadError(f"{where}: a published book is never a source")
    relative = Path(source_file)
    if relative.is_absolute() or ".." in relative.parts or "\\" in source_file:
        raise ClauseLoadError(f"{where}: source_file must be a plain path inside policies/sources")
    # Windows drops a trailing dot or space from a name, so "web./x.pdf" would open web/x.pdf
    # while escaping the web/OCR rules, which read the spelling: refuse such names.
    if any(part != part.strip() or part.endswith(".") for part in relative.parts):
        raise ClauseLoadError(f"{where}: source_file must be a plain path inside policies/sources")
    resolved = (sources_dir / relative).resolve()
    if not resolved.is_relative_to(sources_dir.resolve()) or not resolved.exists():
        raise ClauseLoadError(f"{where}: unknown source_file")
    # Each part must be a real entry name (any case), so a Windows short name ("UAEFED~1.PDF")
    # cannot open a file while escaping the labels, which read the spelling.
    directory = sources_dir
    for part in relative.parts:
        if "~" in part or part.casefold() not in {e.name.casefold() for e in directory.iterdir()}:
            raise ClauseLoadError(f"{where}: source_file must name the file as listed")
        directory = directory / part


def _squash(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())
