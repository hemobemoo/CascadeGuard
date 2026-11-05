"""The engine's check of an LLM-written adviser answer (Ask the Policy Adviser).

The model may only pick clause ids from the evidence it was given and write free text around
them; this deterministic check decides whether that answer may be shown. It never repairs an
answer: any problem rejects it, and the caller shows the deterministic template instead, with
the reasons. Quotes, sources, pages and status labels are never taken from the model: they are
filled from the loaded clause, and every line the model wrote is shown under the engine's
agent-statement label (unverified; not a finding or a legal conclusion).

Free text is checked after normalisation (`normalise`: NFKC, Unicode format and control
characters removed, common Latin look-alikes mapped), so zero-width marks or homoglyphs cannot
hide a word. The patterns are deliberately broad: a false alarm costs only a template answer.

Rules (AGENTS.md "Architecture boundary", "Policy and evidence rules"):
- every cited id is one of the citable clauses retrieved for this question (loaded, reviewed or
  illustrative, scoped to the adviser by `clauses_for_role`), else `unknown_citation`;
- UAE evidence cites only UAE clauses and the international comparison only non-UAE ones
  (`uae_label_mismatch`, `international_label_mismatch`);
- no gap wording: the engine's GAP_CLAIM pattern plus ADVISER_GAP (absent, lacks, unclear, "no
  ... requirement", "does not require", ...), so the answer never says that a provision is
  missing from UAE law (`gap_wording`);
- no status claims in free text (binding, mandatory, "federal law", ...): only the engine's
  status labels say what binds (`status_claim`), so illustrative or unverified material is
  never presented as binding law;
- no authority wording (authorise, approve, permit, waive, override, disregard, ...): the
  adviser advises and never authorises an action or sets aside a prohibition or safeguard
  (`authority_wording`);
- no control or format characters in free text (`control_characters`);
- the responsible role is exactly NOT_ESTABLISHED, or a scenario role id followed by a short
  reason (`responsible_role`);
- an abstention cites nothing, says NOT_IDENTIFIED in its direct answer and lists no options;
  an answer that does not abstain cites at least one clause (`abstention`).
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cascadeguard.domain.policies import PolicyClause, is_uae_jurisdiction
from cascadeguard.engine.constraints import GAP_CLAIM

NOT_ESTABLISHED = "not established in the reviewed corpus"
NOT_IDENTIFIED = "not identified in the reviewed corpus"
MAX_ROLE_REASON = 300

# Latin look-alikes from other scripts and IPA, mapped before matching (NFKC keeps them).
_CONFUSABLES = str.maketrans(
    {
        chr(code): latin
        for code, latin in (
            (0x0261, "g"),  # IPA script g
            (0x0251, "a"),  # IPA alpha
            (0x0430, "a"),  # Cyrillic
            (0x0435, "e"),
            (0x043E, "o"),
            (0x0440, "p"),
            (0x0441, "c"),
            (0x0443, "y"),
            (0x0445, "x"),
            (0x0456, "i"),
            (0x0458, "j"),
            (0x0455, "s"),
            (0x04BB, "h"),
            (0x03BF, "o"),  # Greek
            (0x03B1, "a"),
            (0x03B9, "i"),
        )
    }
)
_INNER_HYPHEN = re.compile(r"(?<=\w)[-\u00ad\u2010\u2011](?=\w)")
ADVISER_GAP = re.compile(
    r"\babsen(?:t|ce)\b|\black(?:s|ing|ed)?\b|\bunclear\b|\bunaddressed\b|\bundefined\b"
    r"|\bmissing\b|\bvoid\b|\bomi(?:ts|tted|ssion)\b"
    r"|\bno (?:\w+ ){0,2}(?:requirements?|statutes?|obligations?|duty|duties|mandates?"
    r"|legislation|provisions?|rules?|laws?)\b"
    r"|\b(?:does|do|did|is|are) ?n[o']t (?:\w+ ){0,2}(?:oblige|require|mandate|specify|say"
    r"|state|assign|define|cover|address|explicit|clear)\w*\b"
    r"|\bnot (?:required|obliged|mandated|specified|assigned|defined) by\b"
    r"|\bnone of\b|\bnobody\b|\bno[- ]one\b|\bfail(?:s|ed)? to\b|\bquiet\b"
    r"|\bnot explicit\w*\b|\bnor does\b|\bneither\b",
    re.IGNORECASE,
)
STATUS_CLAIM = re.compile(
    r"\b(?:non-?|not )?binding\b|\bmandatory\b|\blegally\b|\benforceable\b|\bhas the force of\b"
    r"|\b(?:federal|uae|emirati|dubai) (?:law|legislation|statute|regulation|decree)\b"
    r"|\breviewed\b(?! corpus)|\billustrative\b|\bin force\b|\bin effect\b"
    r"|\bcompulsor\w*|\bobligator\w*|\bstatutor\w*|\blegal(?:ly)? force\b|\bforce of law\b"
    r"|\brequired by (?:the )?law\b|\blaw of the land\b|\blegal (?:duty|obligation|requirement)",
    re.IGNORECASE,
)
AUTHORITY = re.compile(
    r"\bauthori[sz](?:e|es|ed|ing|ation)\b|\bapprov(?:e|es|ed|ing|al)\b|\bhereby\b"
    r"|\bpermit(?:s|ted|ting)?\b|\bpermission\b|\bwaiv(?:e|es|ed|er|ing)\b|\bdisregard\w*\b"
    r"|\boverrid(?:e|es|den|ing)\b|\bset aside\b|\b(?:may|can) (?:be )?ignored?\b"
    r"|\bexempt\w*\b|\bsuspend\w*\b|\ballow(?:s|ed|ing)?\b|\bgo ahead\b|\bgreen light\b"
    r"|\bclear(?:s|ed)? (?:it|to|for)\b|\bcleared\b|\bdoes not apply\b|\bsign(?:s|ed)? off\b"
    r"|\bno (?:\w+ )?escalation\b|\bneed not\b|\bnot need to\b|\bno need to\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AnswerCheck:
    reasons: tuple[str, ...]  # empty: the answer may be shown
    unknown_ids: tuple[str, ...]  # cited ids that were not retrieved citable clauses

    @property
    def ok(self) -> bool:
        return not self.reasons


def normalise(text: str) -> str:
    """Text as matched, on one line: NFKC then case-folded; decomposed (NFKD) with combining
    marks dropped ("bínding" -> "binding"); format and control characters removed; Latin
    look-alikes mapped (after folding, so capitals are covered too); hyphens and soft hyphens
    inside a word removed ("bind-ing" -> "binding")."""
    folded = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).casefold())
    kept = "".join(
        " " if ch in "\n\r\t" else ch
        for ch in folded
        if ch in "\n\r\t"
        or not (unicodedata.category(ch).startswith("C") or unicodedata.category(ch) == "Mn")
    )
    mapped = _INNER_HYPHEN.sub("", kept.translate(_CONFUSABLES))
    return " ".join(mapped.split())


def has_control(text: str) -> bool:
    """Any control, format, private-use or unassigned character, newlines included."""
    return any(unicodedata.category(ch).startswith("C") for ch in text)


def is_uae_clause(clause: PolicyClause) -> bool:
    return is_uae_jurisdiction(clause.jurisdiction)


def responsible_role_ok(text: str, role_ids: Iterable[str]) -> bool:
    """NOT_ESTABLISHED exactly, or a role id as the first word, then a short reason."""
    stripped = normalise(text)
    if stripped == NOT_ESTABLISHED:
        return True
    first = stripped.split(maxsplit=1)[0].rstrip(",;:.-") if stripped else ""
    return first in set(role_ids) and len(stripped) <= MAX_ROLE_REASON


def check_answer(
    *,
    abstain: bool,
    uae_ids: Iterable[str],
    international_ids: Iterable[str],
    direct_answer: str,
    free_text: Iterable[str],
    options: Iterable[str],
    responsible_role: str,
    citable: Mapping[str, PolicyClause],
    role_ids: Iterable[str],
) -> AnswerCheck:
    uae, international = tuple(uae_ids), tuple(international_ids)
    opts = tuple(options)
    cited = (*uae, *international)
    raw = (direct_answer, *free_text, *opts, responsible_role)
    texts = [normalise(t) for t in raw]
    reasons: list[str] = []
    unknown = tuple(dict.fromkeys(i for i in cited if i not in citable))
    if unknown:
        reasons.append("unknown_citation")
    if any(i in citable and not is_uae_clause(citable[i]) for i in uae):
        reasons.append("uae_label_mismatch")
    if any(i in citable and is_uae_clause(citable[i]) for i in international):
        reasons.append("international_label_mismatch")
    if any(GAP_CLAIM.search(t) or ADVISER_GAP.search(t) for t in texts):
        reasons.append("gap_wording")
    if any(STATUS_CLAIM.search(t) for t in texts):
        reasons.append("status_claim")
    if any(AUTHORITY.search(t) for t in texts):
        reasons.append("authority_wording")
    if any(has_control(t) for t in raw):
        reasons.append("control_characters")
    if not responsible_role_ok(responsible_role, role_ids):
        reasons.append("responsible_role")
    abstained_ok = NOT_IDENTIFIED in normalise(direct_answer) and not opts and not cited
    if (abstain and not abstained_ok) or (not abstain and not cited):
        reasons.append("abstention")
    return AnswerCheck(tuple(reasons), unknown)
