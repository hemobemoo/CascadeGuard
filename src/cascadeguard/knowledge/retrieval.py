"""What an agent is told about the rules: the loaded clauses that concern its role, and an
optional keyword search over the extracted PDF text for context.

Clauses are public law, not scenario data, so giving them to a role crosses no information
boundary. Selection uses the engine's own scope rule (decision 7n, `RuleBook.concerns`), so an
agent is shown exactly the clauses it may cite for its allowed actions. Clauses outside the
corpus (hypothetical repair rules in a replay) are shown so an agent can adapt to a repair, but
marked not citable. Extracted PDF text is unreviewed context: never a clause, never citable,
and the two published books are always excluded.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cascadeguard.domain.policies import PolicyClause
from cascadeguard.engine.constraints import RuleBook
from cascadeguard.knowledge.loader import BOOK_MARKERS, EXTRACTED_DIR

NOT_CITABLE_LABEL = "hypothetical repair rule (not a source clause; not citable)"
ANY_ACTION = "any_proposed_action"
# Human decision P5-3 (2026-10-24): this exact label on every snippet sent to an agent.
CONTEXT_LABEL = "context only; not citable"


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


def search_extracted(
    query: str, limit: int = 5, extracted_dir: Path = EXTRACTED_DIR, width: int = 400
) -> tuple[Snippet, ...]:
    """Pages of policies/extracted/ that contain the most query words (case-insensitive).
    Deterministic: ties are broken by file name and page. The books are never searched."""
    words = sorted({w for w in query.casefold().split() if len(w) > 2})
    if not words or limit <= 0:
        return ()
    scored: list[tuple[int, str, int, str]] = []
    for path in sorted(extracted_dir.glob("*.jsonl")):
        if _is_book(path.name):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            page = json.loads(line)
            source, number, text = str(page["source_file"]), int(page["page"]), str(page["text"])
            if _is_book(source):
                continue
            folded = text.casefold()
            score = sum(folded.count(w) for w in words)
            if score:
                scored.append((-score, source, number, text))
    scored.sort(key=lambda s: s[:3])
    snippets: list[Snippet] = []
    for _, source, number, text in scored[:limit]:
        folded = text.casefold()
        first = min(i for w in words if (i := folded.find(w)) >= 0)
        start = max(0, first - width // 4)
        snippets.append(Snippet(source, number, " ".join(text[start : start + width].split())))
    return tuple(snippets)
