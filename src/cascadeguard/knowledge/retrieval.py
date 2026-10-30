"""What an agent is told about the rules: the loaded clauses that concern its role, and an
optional keyword search over the extracted PDF text for context.

Clauses are public law, not scenario data, so giving them to a role crosses no information
boundary. Selection uses the engine's own scope rule (decision 7n, `RuleBook.concerns`), so an
agent is shown exactly the clauses it may cite for its allowed actions. Clauses outside the
corpus (hypothetical repair rules in a replay) are shown so an agent can adapt to a repair, but
marked not citable. Extracted PDF text is unreviewed context: never a clause, never citable,
and the two published books and NOT_SEARCHED (the TRA-era cyber strategy, the news item on the
2025 strategy, the superseded web copies of UNESCO and OECD, the TDRA original whose OCR copy is
searched instead, and the Charter's unreliable text layer) are always excluded. For a source
whose text layer is unreliable, only its reviewed page-image transcriptions are searched, and
only while each matches the digest the human pinned (`reviewed_transcriptions`). A web
transcription is served without the human's YAML header at its top.
"""

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from cascadeguard.domain.policies import TRANSCRIBED_SOURCES, WEB_FLAG, PolicyClause
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.knowledge.loader import (
    APPROVALS_FILE,
    BOOK_MARKERS,
    EXTRACTED_DIR,
    TRANSCRIPTIONS_DIR,
    reviewed_transcriptions,
)

NOT_CITABLE_LABEL = "hypothetical repair rule (not a source clause; not citable)"
ANY_ACTION = "any_proposed_action"
# Human decision P5-3 (2026-10-24): this exact label on every snippet sent to an agent.
CONTEXT_LABEL = "context only; not citable"
# A snippet from a web transcription (policies/sources/web/) says so (human decision 2026-10-28).
WEB_CONTEXT_LABEL = f"{WEB_FLAG}; {CONTEXT_LABEL}"
# A snippet from a reviewed page-image transcription says so (human decision 2026-10-29).
TRANSCRIPTION_CONTEXT_LABEL = f"transcribed from page image, reviewed; {CONTEXT_LABEL}"
# OCR text is not checked against the page image (human decision 2026-10-30, PR 3 review).
OCR_CONTEXT_LABEL = f"OCR text, unchecked; {CONTEXT_LABEL}"
# Kept as provenance but never searched. The TRA-era strategy (human decision 2026-10-28) is
# superseded by the 2025 strategy, and its extraction is unreliable (p.5, pp.6-16). Web page 03
# (human decision 2026-10-29) is a news item about the 2025 strategy, not the strategy's text.
# TRANSCRIBED_SOURCES (the Charter; human decision 2026-10-29) have an unreliable text layer:
# only their reviewed transcriptions are searched. Human decisions 2026-10-30 (PR 3 review): web
# 06 and 07 are superseded by their official originals (web/MANIFEST.md); of the two TDRA copies
# only the OCR one is searched, since the original has no text layer on pp.13-47.
NOT_SEARCHED = frozenset(
    {
        "UAE_National_Cybersecurity_Strategy.pdf",
        "web/03_uae_national_cybersecurity_strategy.pdf",
        "web/06_unesco_ai_ethics_recommendation.pdf",
        "web/07_oecd_ai_principles.pdf",
        "887026278-TDRA-Telecom-Law-Final-English-o.pdf",
    }
    | TRANSCRIBED_SOURCES
)
# The human's metadata block at the top of a web transcription (MANIFEST.md): a "YAML" line,
# `key: "value"` lines, then the note ending "verify clauses before marking them reviewed ."
_WEB_HEADER = re.compile(
    r"\AYAML\n(?:[a-z_]+: .*\n)+(?:(?:(?!\n).)*\n){0,3}?.*marking them reviewed \.[^\n]*"
)
NOT_SEARCHED_STEMS = frozenset(Path(name).stem.casefold() for name in NOT_SEARCHED)


@dataclass(frozen=True, slots=True)
class RoleClause:
    id: str
    title: str
    status_label: str  # the clause's label, or NOT_CITABLE_LABEL for a repair rule
    text: str
    reading: str  # the engine's normalized reading in one line, or "" if none
    citable: bool
    # The engine's 7n rule, per clause: the actions whose proposal (in the same decision) makes
    # it citable. ANY_ACTION: citable with any proposed action (it names this role).
    cite_with: tuple[str, ...] = ()


def _reading(clause: PolicyClause) -> str:
    n = clause.normalized
    if n is None:
        return ""
    parts = [f"{n.kind.value}: {n.actor} {n.action}"]
    if n.counterpart:
        parts.append(f"counterpart {n.counterpart}")
    if n.data_category:
        parts.append(f"data category {n.data_category}")
    if n.condition:
        parts.append(f"condition: {n.condition}")
    if n.deadline_minutes is not None:
        parts.append(f"within {n.deadline_minutes} minutes")
    return "; ".join(parts)


def clauses_for_role(
    clauses: Mapping[str, PolicyClause],
    corpus_ids: frozenset[str],
    role_id: str,
    allowed_actions: tuple[str, ...],
) -> tuple[RoleClause, ...]:
    """Loaded clauses that concern this role or one of its allowed actions, sorted by id, each
    with the proposed actions it may be cited with (`cite_with`, from `RuleBook.concerns`)."""
    book = RuleBook(dict(clauses))

    def cite_with(cid: str) -> tuple[str, ...]:
        if book.concerns(cid, role_id, ()):
            return (ANY_ACTION,)
        return tuple(a for a in allowed_actions if book.concerns(cid, role_id, (a,)))

    return tuple(
        RoleClause(
            id=c.id,
            title=c.title,
            status_label=c.status_label if c.id in corpus_ids else NOT_CITABLE_LABEL,
            text=" ".join(c.text.split()),
            reading=_reading(c),
            citable=c.id in corpus_ids,
            cite_with=cite_with(c.id) if c.id in corpus_ids else (),
        )
        for c in sorted(clauses.values(), key=lambda c: c.id)
        if book.concerns(c.id, role_id, allowed_actions)
    )


def clauses_by_action(role_clauses: tuple[RoleClause, ...]) -> dict[str, list[str]]:
    """Citable clause ids grouped by the proposed action that makes them citable."""
    groups: dict[str, list[str]] = {}
    for c in role_clauses:
        for action in c.cite_with:
            groups.setdefault(action, []).append(c.id)
    return groups


@dataclass(frozen=True, slots=True)
class Snippet:
    source_file: str
    page: int
    text: str
    label: str = CONTEXT_LABEL


def _is_book(name: str) -> bool:
    return any(marker in name.casefold() for marker in BOOK_MARKERS)


def _not_searched(name: str) -> bool:
    """A book, or a document kept out of the search (NOT_SEARCHED), by file or source name."""
    return _is_book(name) or Path(name).stem.casefold() in NOT_SEARCHED_STEMS


def searchable_pages(
    extracted_dir: Path = EXTRACTED_DIR,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
    approvals_file: Path = APPROVALS_FILE,
) -> Iterator[Snippet]:
    """Every searchable page, whole, with its label: the extracted text in file and line order
    (books and NOT_SEARCHED excluded), then the reviewed transcriptions. The one corpus for the
    keyword search and the vector index (knowledge.kb)."""
    for path in sorted(extracted_dir.glob("*.jsonl")):
        if _not_searched(path.name):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            page = json.loads(line)
            source, number, text = str(page["source_file"]), int(page["page"]), str(page["text"])
            if _not_searched(source):
                continue
            if page.get("web") is True:
                text, label = without_web_header(text), WEB_CONTEXT_LABEL
            else:
                label = OCR_CONTEXT_LABEL if page.get("ocr") is True else CONTEXT_LABEL
            yield Snippet(source, number, text, label)
    for page in reviewed_transcriptions(transcriptions_dir, approvals_file):
        source, number, text = str(page["source_file"]), int(str(page["page"])), str(page["text"])
        yield Snippet(source, number, text, TRANSCRIPTION_CONTEXT_LABEL)


def without_web_header(text: str) -> str:
    """The page with its web metadata header blanked: each character becomes a space (line breaks
    kept), so character spans into the page still hold."""
    match = _WEB_HEADER.match(text)
    if match is None:
        return text
    head = re.sub(r"[^\n]", " ", match.group())
    return head + text[match.end() :]


def query_words(query: str) -> list[str]:
    """The keyword search's query words: case-folded, longer than two letters, sorted."""
    return sorted({w for w in query.casefold().split() if len(w) > 2})


def keyword_score(text: str, words: list[str]) -> int:
    """How often the query words occur in the text (case-insensitive)."""
    folded = text.casefold()
    return sum(folded.count(w) for w in words)


@cache
def extracted_digest(
    extracted_dir: Path = EXTRACTED_DIR,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
    approvals_file: Path = APPROVALS_FILE,
) -> str:
    """Digest of the searchable text exactly as served (`searchable_pages`: source, page, text
    and label), so a changed corpus or serving rule never reuses a decision. Snippets are not
    part of a view, so this goes into the prompt version. Built from the parsed records, so line
    endings (CRLF checkouts on Windows) do not change it."""
    digest = hashlib.sha256()
    for page in searchable_pages(extracted_dir, transcriptions_dir, approvals_file):
        record = [page.source_file, page.page, page.text, page.label]
        digest.update(json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n")
    return digest.hexdigest()[:12]


def search_extracted(
    query: str,
    limit: int = 5,
    extracted_dir: Path = EXTRACTED_DIR,
    width: int = 400,
    transcriptions_dir: Path = TRANSCRIPTIONS_DIR,
    approvals_file: Path = APPROVALS_FILE,
) -> tuple[Snippet, ...]:
    """Pages of policies/extracted/ and reviewed transcriptions that contain the most query words
    (case-insensitive). Deterministic: ties are broken by file name and page. The books and
    NOT_SEARCHED are never searched in the extracted text."""
    words = query_words(query)
    if not words or limit <= 0:
        return ()
    scored: list[tuple[int, str, int, str, str]] = []
    for page in searchable_pages(extracted_dir, transcriptions_dir, approvals_file):
        score = keyword_score(page.text, words)
        if score:
            scored.append((-score, page.source_file, page.page, page.text, page.label))
    scored.sort(key=lambda s: s[:3])
    snippets: list[Snippet] = []
    for _, source, number, text, label in scored[:limit]:
        folded = text.casefold()
        first = min(i for w in words if (i := folded.find(w)) >= 0)
        start = max(0, first - width // 4)
        excerpt = " ".join(text[start : start + width].split())
        snippets.append(Snippet(source, number, excerpt, label))
    return tuple(snippets)
