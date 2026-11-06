"""The engine's check of an LLM-written adviser answer (Ask the Policy Adviser).

The model may only pick clause ids from the evidence it was given and write free text around
them; this deterministic check decides what of that answer may be shown. It never repairs an
answer. Two levels (human decision 2026-11-06, "adviser-commentary-check"):
- `check_answer`, the answer's structure (citations, UAE/international split, responsible role,
  abstention, control characters): any problem rejects the whole answer, and the caller shows
  the deterministic template instead, with the reasons;
- `sentence_reasons`, the model's free text, one sentence at a time (gap, status and authority
  wording): a flagged sentence is withheld from the commentary and counted with its reasons;
  the other sentences are shown.
Quotes, sources, pages and status labels are never taken from the model: they are filled from
the loaded clause, and every sentence the model wrote is shown under the engine's
agent-statement label (unverified; not a finding or a legal conclusion).

Free text is checked after normalisation (`normalise`: NFKC, Unicode format and control
characters removed, common Latin look-alikes mapped), so zero-width marks or homoglyphs cannot
hide a word. The patterns are deliberately broad: a false alarm costs only a template answer.

Rules (AGENTS.md "Architecture boundary", "Policy and evidence rules"). Whole answer:
- every cited id is one of the citable clauses retrieved for this question (loaded, reviewed or
  illustrative, scoped to the adviser by `clauses_for_role`), else `unknown_citation`;
- UAE evidence cites only UAE clauses and the international comparison only non-UAE ones
  (`uae_label_mismatch`, `international_label_mismatch`);
- no control or format characters in free text (`control_characters`);
- the responsible role is exactly NOT_ESTABLISHED, or a scenario role id followed by a short
  reason (`responsible_role`);
- an abstention cites nothing, says NOT_IDENTIFIED in its direct answer and lists no options;
  an answer that does not abstain cites at least one clause (`abstention`).
Each sentence:
- no gap wording: the engine's GAP_CLAIM pattern plus ADVISER_GAP (absent, lacks, unclear, "no
  ... requirement", "does not require", ...), so the answer never says that a provision is
  missing from UAE law (`gap_wording`). Allowed: a statement scoped to the evidence the model
  was given (EVIDENCE_SCOPED: "not identified in the provided evidence", "the retrieved clauses
  do not address"); the rest of the sentence is still checked;
- no status claims (binding, mandatory, "federal law", ...): only the engine's status labels
  say what binds (`status_claim`), so illustrative or unverified material is never presented as
  binding law. Allowed: a part of the status label of the clause the sentence is about (its own
  clause for a relevance note; else the clauses it names by id; else a part every cited clause's
  label has), e.g. "illustrative" or "not binding", never the bare word "binding";
- no authority wording (authorise, approve, permit, waive, override, disregard, ...): the
  adviser advises and never authorises an action or sets aside a prohibition or safeguard
  (`authority_wording`).
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from cascadeguard.domain.policies import LABEL_SEPARATOR, PolicyClause, is_uae_jurisdiction
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
    r"|\bnot explicit\w*\b|\bnor does\b|\bneither\b"
    r"|\bno (?:\w+ ){0,2}(?:clauses?|instruments?|texts?|deadlines?|time limits?|owners?)\b"
    r"|\bonly foreign\b",
    re.IGNORECASE,
)
STATUS_CLAIM = re.compile(
    r"\b(?:non-?|not )?binding\b|\bmandatory\b|\blegally\b|\benforceable\b|\bhas the force of\b"
    r"|\b(?:federal|uae|emirati|dubai) (?:law|legislation|statute|regulation|decree)\b"
    r"|\breviewed\b(?! corpus)|\billustrative\b|\bin force\b|\bin effect\b"
    r"|\bcompulsor\w*|\bobligator\w*|\bstatutor\w*|\blegal(?:ly)? force\b|\bforce of law\b"
    r"|\brequired by (?:the )?law\b|\blaw of the land\b|\blegal (?:duty|obligation|requirement)"
    r"|\bis (?:the )?law\b|\b(?:legal )?weight of law\b|\blegal weight\b|\bbound by\b"
    r"|\b(?:emirate|state|country)'?s? law\b|\bunder the law\b|\blaw of the uae\b"
    r"|\blawful(?:ly)?\b|\bunlawful\b|\blegal(?:ly)? required\b",
    re.IGNORECASE,
)
AUTHORITY = re.compile(
    r"\bauthori[sz](?:e|es|ed|ing|ation)\b|\bapprov(?:e|es|ed|ing|al)\b|\bhereby\b"
    r"|\bpermit(?:s|ted|ting)?\b|\bpermission\b|\bwaiv(?:e|es|ed|er|ing)\b|\bdisregard\w*\b"
    r"|\boverrid(?:e|es|den|ing)\b|\bset aside\b|\b(?:may|can) (?:be )?ignored?\b"
    r"|\bexempt\w*\b|\bsuspend\w*\b|\ballow(?:s|ed|ing)?\b|\bgo ahead\b|\bgreen light\b"
    r"|\bclear(?:s|ed)? (?:it|to|for)\b|\bcleared\b|\bdoes not apply\b|\bsign(?:s|ed)? off\b"
    r"|\bno (?:\w+ )?escalation\b|\bneed not\b|\bnot need to\b|\bno need to\b"
    r"|\bentitled\b|\bfree to\b|\bmay proceed\b|\bproceed to\b|\bbypass\w*\b|\bskip\w*\b"
    r"|\bcircumvent\w*\b|\bsidestep\w*\b",
    re.IGNORECASE,
)


# Absence stated about the evidence the model was given, not about the law (human decision
# 2026-11-06): removed before the gap patterns run, so the rest of the sentence is still checked.
EVIDENCE = r"(?:provided|retrieved|listed|cited) (?:evidence|clauses?)"
EVIDENCE_SCOPED = re.compile(
    rf"\bnot (?:identified|stated|named|specified|addressed) (?:in|by) the {EVIDENCE}\b"
    rf"|\b(?:the )?{EVIDENCE} (?:does|do) not (?:address|state|specify|name|identify)\b"
)
NOT_SCOPED_LABEL = "binding"  # a label part never allowed alone: it would assert binding force
# A sentence ends at ".", "!" or "?" followed by a space (ids such as dha.pp11.4-18-1 have none).
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


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


def sentences(text: str) -> list[str]:
    """The text split into sentences, each on one line; empty parts dropped."""
    return [" ".join(p.split()) for p in _SENTENCE_END.split(text) if p.strip()]


def label_parts(clause: PolicyClause) -> frozenset[str]:
    """The parts of a clause's status label a sentence may repeat ("illustrative", "reviewed",
    "not binding", "foreign precedent", ...), normalised; never the bare word "binding"."""
    parts = {str(clause.status), *clause.status_label.split(LABEL_SEPARATOR)}
    return frozenset(normalise(p) for p in parts if normalise(p) != NOT_SCOPED_LABEL)


def allowed_label_parts(
    sentence: str, own: str | None, cited: Mapping[str, PolicyClause]
) -> frozenset[str]:
    """Label parts the sentence may repeat: those of its own clause (a relevance note); else of
    the cited clauses it names by id; else the parts every cited clause's label has."""
    if own is not None:
        return label_parts(cited[own])
    named = [label_parts(c) for cid, c in cited.items() if cid in sentence]
    if named:
        return frozenset(part for parts in named for part in parts)
    every = [label_parts(c) for c in cited.values()]
    common: set[str] = set(every[0]) if every else set()
    for parts in every[1:]:
        common &= parts
    return frozenset(common)


def _without(text: str, parts: Iterable[str]) -> str:
    for part in sorted(parts, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(part)}(?!\w)", " ", text)
    return text


def sentence_reasons(sentence: str, allowed_labels: Iterable[str] = ()) -> tuple[str, ...]:
    """Why one sentence of model free text must be withheld (empty: it may be shown)."""
    text = normalise(sentence)
    reasons: list[str] = []
    scoped = EVIDENCE_SCOPED.sub(" ", text)
    if GAP_CLAIM.search(scoped) or ADVISER_GAP.search(scoped):
        reasons.append("gap_wording")
    if STATUS_CLAIM.search(_without(text, allowed_labels)):
        reasons.append("status_claim")
    if AUTHORITY.search(text):
        reasons.append("authority_wording")
    return tuple(reasons)


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
    """The answer's structure. Gap, status and authority wording are checked per sentence
    (`sentence_reasons`), not here."""
    uae, international = tuple(uae_ids), tuple(international_ids)
    opts = tuple(options)
    cited = (*uae, *international)
    raw = (direct_answer, *free_text, *opts, responsible_role)
    reasons: list[str] = []
    unknown = tuple(dict.fromkeys(i for i in cited if i not in citable))
    if unknown:
        reasons.append("unknown_citation")
    if any(i in citable and not is_uae_clause(citable[i]) for i in uae):
        reasons.append("uae_label_mismatch")
    if any(i in citable and is_uae_clause(citable[i]) for i in international):
        reasons.append("international_label_mismatch")
    if any(has_control(t) for t in raw):
        reasons.append("control_characters")
    if not responsible_role_ok(responsible_role, role_ids):
        reasons.append("responsible_role")
    # An abstention cites nothing, lists no options and names no role; its text is replaced by
    # the engine's fixed abstention sentence when shown (by the adviser module).
    abstained_ok = (
        NOT_IDENTIFIED in normalise(direct_answer)
        and not opts
        and not cited
        and normalise(responsible_role) == NOT_ESTABLISHED
    )
    if (abstain and not abstained_ok) or (not abstain and not cited):
        reasons.append("abstention")
    return AnswerCheck(tuple(reasons), unknown)
