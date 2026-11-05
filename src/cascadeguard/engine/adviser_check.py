"""The engine's check of an LLM-written adviser answer (Ask the Policy Adviser).

The model may only pick clause ids from the evidence it was given and write free text around
them; this deterministic check decides whether that answer may be shown. It never repairs an
answer: any problem rejects it, and the caller shows the deterministic template instead, with
the reasons. Quotes, sources, pages and status labels are never taken from the model: they are
filled from the loaded clause.

Rules (AGENTS.md "Architecture boundary", "Policy and evidence rules"):
- every cited id is one of the citable clauses retrieved for this question (loaded, reviewed or
  illustrative, scoped to the adviser by `clauses_for_role`), else `unknown_citation`;
- UAE evidence cites only UAE clauses and the international comparison only non-UAE ones, so
  the two are never mixed (`uae_label_mismatch`, `international_label_mismatch`);
- no gap wording in free text (the engine's GAP_CLAIM pattern), so the answer never says that a
  provision is missing from UAE law (`gap_wording`);
- the responsible role is a scenario role id, optionally followed by an explanation, or exactly
  NOT_ESTABLISHED (`responsible_role`);
- an abstention cites nothing, and an answer that does not abstain cites at least one clause
  (`abstention`).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cascadeguard.domain.policies import PolicyClause, is_uae_jurisdiction
from cascadeguard.engine.constraints import GAP_CLAIM

NOT_ESTABLISHED = "not established in the reviewed corpus"


@dataclass(frozen=True, slots=True)
class AnswerCheck:
    reasons: tuple[str, ...]  # empty: the answer may be shown
    unknown_ids: tuple[str, ...]  # cited ids that were not retrieved citable clauses

    @property
    def ok(self) -> bool:
        return not self.reasons


def is_uae_clause(clause: PolicyClause) -> bool:
    return is_uae_jurisdiction(clause.jurisdiction)


def responsible_role_ok(text: str, role_ids: Iterable[str]) -> bool:
    """NOT_ESTABLISHED exactly, or a role id as the first word (then any explanation)."""
    stripped = text.strip()
    if stripped == NOT_ESTABLISHED:
        return True
    first = stripped.split(maxsplit=1)[0].rstrip(",;:.") if stripped else ""
    return first in set(role_ids)


def check_answer(
    *,
    abstain: bool,
    uae_ids: Iterable[str],
    international_ids: Iterable[str],
    free_text: Iterable[str],
    responsible_role: str,
    citable: Mapping[str, PolicyClause],
    role_ids: Iterable[str],
) -> AnswerCheck:
    uae, international = tuple(uae_ids), tuple(international_ids)
    cited = (*uae, *international)
    reasons: list[str] = []
    unknown = tuple(dict.fromkeys(i for i in cited if i not in citable))
    if unknown:
        reasons.append("unknown_citation")
    if any(i in citable and not is_uae_clause(citable[i]) for i in uae):
        reasons.append("uae_label_mismatch")
    if any(i in citable and is_uae_clause(citable[i]) for i in international):
        reasons.append("international_label_mismatch")
    if any(GAP_CLAIM.search(t) for t in (*free_text, responsible_role)):
        reasons.append("gap_wording")
    if not responsible_role_ok(responsible_role, role_ids):
        reasons.append("responsible_role")
    if abstain == bool(cited):
        reasons.append("abstention")
    return AnswerCheck(tuple(reasons), unknown)
