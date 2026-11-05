"""Ask the Policy Adviser: pause at a step T+n and put a question to the policy_legal_adviser.

Read-only. The question never changes the run: the answer is built from the adviser's own
`RoleView` at that step in the governed scripted baseline (`simulation/boundaries.py`), so it
holds no fact released after T+n and nothing outside the adviser's boundary. A fact that is not
in the view is reported as not available to the adviser at this step, never as non-existent.

Evidence has two kinds, kept apart everywhere:
- Citable: the loaded clauses scoped to the adviser (`RoleView.role_clauses`, from
  `clauses_for_role`: reviewed and illustrative only), ranked against the question by a
  deterministic word match. Quote, source, page and status label always come from the loaded
  clause, never from a model.
- Context, labelled "context only; not citable": knowledge-base chunks from the existing hybrid
  search. A preset question uses its stored query vector (embedded once with the manifest's
  model), a free-text question is embedded live when a key is set, and with no key only the
  keyword half runs, which the answer says.

Answer modes:
- LLM (a key is set): the configured chat model writes the seven sections from this evidence
  only; `engine/adviser_check.py` validates the citations and wording; the answer is cached
  (`data/adviser_cache/` by default) and replays with offline mode.
- Template (no key, offline with no cached answer, or an LLM answer the engine rejected): a
  deterministic template fills the seven sections from the retrieved clauses. No network.
"""

import hashlib
import json
import math
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import yaml
from dotenv import dotenv_values
from pydantic import Field, ValidationError

import cascadeguard.agents.llm as llm
from cascadeguard.agents.cache import canonical_view
from cascadeguard.agents.llm import (
    ATTEMPTS,
    LLMConfig,
    _content,  # pyright: ignore[reportPrivateUsage]
    _strict,  # pyright: ignore[reportPrivateUsage]
)
from cascadeguard.domain.base import DomainModel
from cascadeguard.domain.policies import ClauseStatus, PolicyClause, is_uae_jurisdiction
from cascadeguard.engine.adviser_check import (
    NOT_ESTABLISHED,
    NOT_IDENTIFIED,
    AnswerCheck,
    check_answer,
)
from cascadeguard.engine.constraints import agent_statement
from cascadeguard.knowledge import kb
from cascadeguard.knowledge.loader import PROJECT_ROOT
from cascadeguard.knowledge.retrieval import CONTEXT_LABEL
from cascadeguard.simulation.boundaries import RoleView

ADVISER = "policy_legal_adviser"
PROMPT_VERSION = "adviser-v1"
DEFAULT_ANSWER_CACHE = PROJECT_ROOT / "data" / "adviser_cache"
PRESETS_FILE = "adviser_questions.yaml"
PRESET_VECTORS = "adviser_query_vectors.json"  # in policies/kb/, tied to the index digest
MAX_UAE = 3
MAX_INTERNATIONAL = 2
LLM_CANDIDATES = 8  # citable clauses offered to the model
CONTEXT_K = 3
RELEVANCE_BONUS = 1.0  # ordering only, for a clause quoted by a retrieved context chunk
REQUEST_CAP = 2 * ATTEMPTS  # requests per question, retries included

MODE_LLM = "llm"
MODE_TEMPLATE = "template"
LLM_LIVE = "LLM (configured chat model, live call; cached)"
LLM_ABSTAINED = "LLM (the model abstained; the engine's fixed abstention text is shown)"
LLM_CACHED = "LLM (configured chat model; cached answer, no call)"
TEMPLATE_NO_KEY = "deterministic template (no API key)"
TEMPLATE_OFFLINE = "deterministic template (offline; no cached LLM answer for this question)"
TEMPLATE_NO_MODEL = (
    "deterministic template (CASCADEGUARD_MODEL is not set; no default model is used)"
)
SUGGESTION = "suggestion, not a permission: "
TEMPLATE_NO_CLIENT = "deterministic template (no chat client; no cached LLM answer)"
TEMPLATE_REJECTED = "deterministic template (the engine rejected the LLM answer: {reasons})"
TEMPLATE_FAILED = "deterministic template, as with no API key (the live call failed: {reason})"

RETRIEVAL_LIVE = "hybrid search (question embedded live with the knowledge-base model)"
RETRIEVAL_STORED = "hybrid search (stored query vector of a preset question)"
RETRIEVAL_CACHED = "hybrid search (query vector embedded live earlier, from the answer cache)"
RETRIEVAL_KEYWORD = (
    "keyword search only (no query vector: no API key, or offline with none stored; the vector "
    "half of the hybrid search did not run)"
)
KEYWORD_NOTE = "Context was found by keyword search only: no query vector for this question."

UAE_HEADING = "UAE evidence (illustrative scenario rules marked as such)"
INTERNATIONAL_HEADING = "International comparison (not UAE law; listed separately)"
INTERNATIONAL_NOTE = (
    "International and foreign texts are shown for comparison only. Each one's status label "
    "says whether it binds in the UAE."
)
ESCALATION = (
    "The Policy and Legal Adviser has no enforcement authority: it advises; it cannot authorise, "
    "permit or block any action.",
    "Any action that changes access, shares data or activates a channel is decided by the "
    "responsible institution's human decision-maker, and the engine checks it against the "
    "loaded clauses.",
)

# Words that carry no subject matter in a question (matched after folding and stemming).
_STOPWORDS_TEXT = """
a about after again all also an and any are as at be been before being between both but by can
could did do does doing done during each for from had has have having how if in into is it its
may me might must my no nor not of on once only or other our out over own same say said shall
should so some such than that the their them then there these they this those through to too
under until up upon very was we were what when where which while who whom whose why will with
within without would you your
"""
STOPWORDS = frozenset(_STOPWORDS_TEXT.split())
_WORD = re.compile(r"[a-z0-9]+")


def stem(word: str) -> str:
    """A crude, deterministic stem: enough to match "shared", "share" and "sharing", or
    "lockouts" and "lockout". A final "e" is dropped after the suffix."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word[:-1] if len(word) > 4 and word.endswith("e") else word


def content_stems(text: str) -> frozenset[str]:
    words = _WORD.findall(text.casefold().replace("_", " "))
    return frozenset(stem(w) for w in words if w not in STOPWORDS and len(w) > 2)


# --- Evidence ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """A citable clause retrieved for the question, filled from the loaded clause."""

    clause_id: str
    title: str
    status_label: str
    source_file: str | None  # None for an illustrative clause (no source)
    page: int | None
    article: str | None
    quote: str  # the clause text: verbatim for a sourced clause; paraphrase if illustrative
    jurisdiction: str
    uae: bool
    illustrative: bool
    reading: str  # the engine's normalized reading, "" if none
    matched: tuple[str, ...]  # question stems found in the clause
    score: float  # summed IDF weight of the matched stems (rank_clauses)
    relevance: str = ""  # LLM mode: the model's note (an agent statement, unverified)

    @property
    def source(self) -> str:
        if self.illustrative:
            return "illustrative scenario rule: no source document; text is a paraphrase"
        where = f"{self.source_file}, p.{self.page}"
        return f"{where}, {self.article}" if self.article else where


@dataclass(frozen=True, slots=True)
class ContextItem:
    """A knowledge-base chunk: context only, never citable."""

    chunk_id: str
    source_file: str
    page: int
    label: str
    text: str
    clause_ids: tuple[str, ...]  # the adviser's citable clauses quoted in this chunk


@dataclass(frozen=True, slots=True)
class Retrieved:
    candidates: tuple[EvidenceItem, ...]  # citable clauses that match, best first
    context: tuple[ContextItem, ...]
    retrieval: str


def _evidence(clause: PolicyClause, reading: str, matched: frozenset[str]) -> EvidenceItem:
    return EvidenceItem(
        clause_id=clause.id,
        title=clause.title,
        status_label=clause.status_label,
        source_file=clause.source_file,
        page=clause.page,
        article=clause.article,
        quote=" ".join(clause.text.split()),
        jurisdiction=clause.jurisdiction,
        uae=is_uae_jurisdiction(clause.jurisdiction),
        illustrative=clause.status is ClauseStatus.ILLUSTRATIVE,
        reading=reading,
        matched=tuple(sorted(matched)),
        score=0.0,
    )


def rank_clauses(
    question: str,
    view: RoleView,
    clauses: Mapping[str, PolicyClause],
    context: Sequence[ContextItem] = (),
) -> tuple[EvidenceItem, ...]:
    """The adviser's citable clauses that match the question, best first. Deterministic, no
    network. A clause's words are its title, text and engine reading; each question stem found
    there weighs log(N / df), N the adviser's citable clauses and df those holding the stem, so
    a word in every clause ("health") counts little and a rare one ("fallback") much. A clause
    is relevant when its weight reaches log(N), the weight of one word found in that clause
    alone. Ordering only: a clause quoted by a retrieved context chunk gets RELEVANCE_BONUS
    (context alone never makes a clause relevant). Ties: clause id."""
    wanted = content_stems(question)
    words: dict[str, frozenset[str]] = {}
    for rc in view.role_clauses:
        clause = clauses.get(rc.id)
        if rc.citable and clause is not None and clause.status is not ClauseStatus.DRAFT:
            words[rc.id] = content_stems(" ".join((rc.title, rc.text, rc.reading)))
    if not wanted or not words:
        return ()
    n = len(words)
    df = {t: sum(1 for w in words.values() if t in w) for t in wanted}
    threshold = round(math.log(n), 6)
    quoted = {cid for c in context for cid in c.clause_ids}
    scored: list[tuple[float, str, EvidenceItem]] = []
    for cid, clause_words in words.items():
        matched = wanted & clause_words
        weight = round(sum(math.log(n / df[t]) for t in matched), 6)
        if not matched or weight < threshold:
            continue
        reading = next(rc.reading for rc in view.role_clauses if rc.id == cid)
        item = replace(_evidence(clauses[cid], reading, matched), score=weight)
        bonus = RELEVANCE_BONUS if cid in quoted else 0.0
        scored.append((-(weight + bonus), cid, item))
    scored.sort(key=lambda s: s[:2])
    return tuple(item for _, _, item in scored)


def retrieve_context(
    question: str, view: RoleView, embedder: kb.Embedder | None, index: kb.Index | None = None
) -> tuple[ContextItem, ...]:
    """CONTEXT_K knowledge-base chunks: the hybrid search with an embedder, else its keyword
    half. A chunk names only the adviser's own citable clauses."""
    if embedder is not None:
        hits = kb.search_kb(question, k=CONTEXT_K, index=index, embedder=embedder)
    else:
        hits = kb.search_kb_keyword(question, k=CONTEXT_K, index=index)
    own = {c.id for c in view.role_clauses if c.citable}
    return tuple(
        ContextItem(
            h.chunk.id,
            h.chunk.source_file,
            h.chunk.page,
            h.chunk.label,
            h.chunk.text,
            tuple(r.id for r in h.chunk.clauses if r.id in own),
        )
        for h in hits
    )


# --- The answer ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdviserAnswer:
    scenario: str
    question: str
    minute: int
    view_digest: str  # sha256 of the adviser's view at this step (canonical JSON), 16 hex
    mode: str  # MODE_LLM or MODE_TEMPLATE
    mode_detail: str
    retrieval: str
    abstained: bool
    direct_answer: str
    uae_evidence: tuple[EvidenceItem, ...]
    status_labels: tuple[tuple[str, str], ...]  # (clause id, status label) of every cited clause
    international: tuple[EvidenceItem, ...]
    responsible_role: str
    options: tuple[str, ...]
    escalation: tuple[str, ...]
    uncertainty: tuple[str, ...]
    facts_in_view: tuple[str, ...]  # fact ids in the adviser's view at this step
    retrieved: tuple[str, ...]  # citable clause ids retrieved (scores in the trace)
    context: tuple[ContextItem, ...]
    rejected: tuple[str, ...] = ()  # engine reasons, when an LLM answer was rejected
    unknown_citations: tuple[str, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def cited_ids(self) -> tuple[str, ...]:
        return tuple(e.clause_id for e in (*self.uae_evidence, *self.international))

    def sections(self) -> list[tuple[str, list[str]]]:
        """The seven sections as plain lines, in order."""

        def item(e: EvidenceItem) -> list[str]:
            lines = [f"{e.clause_id} [{e.status_label}]: {e.title}", f"  source: {e.source}"]
            kind = "text (paraphrase, not a quotation)" if e.illustrative else "quote"
            lines.append(f'  {kind}: "{e.quote}"')
            if e.relevance:
                lines.append(f"  relevance: {e.relevance}")
            return lines

        uae = [line for e in self.uae_evidence for line in item(e)] or [
            f"Relevant UAE clause: {NOT_IDENTIFIED}."
        ]
        international = [INTERNATIONAL_NOTE] + (
            [line for e in self.international for line in item(e)]
            or [f"Relevant international or foreign clause: {NOT_IDENTIFIED}."]
        )
        return [
            ("1. Direct answer", [self.direct_answer]),
            (f"2. {UAE_HEADING} (clause ID, source, page, verbatim quote)", uae),
            (
                "3. Status label",
                [f"{cid}: {label}" for cid, label in self.status_labels] or ["nothing cited"],
            ),
            (f"4. {INTERNATIONAL_HEADING}", international),
            ("5. Responsible role", [self.responsible_role]),
            (
                "6. Permissible options and required human escalation",
                [*self.options, *self.escalation],
            ),
            ("7. Uncertainty", list(self.uncertainty)),
        ]

    def trace(self) -> dict[str, Any]:
        """Everything needed to audit the answer: inputs, retrieval, validation and output."""
        data = asdict(self)
        data["sections"] = [{"title": t, "lines": lines} for t, lines in self.sections()]
        data["context_label"] = CONTEXT_LABEL
        return data

    def text(self) -> str:
        head = [
            f"Ask the Policy Adviser: {self.scenario} at T+{self.minute:02d}",
            f"Question: {self.question}",
            f"Answer mode: {self.mode_detail}",
            f"Retrieval: {self.retrieval}",
            f"Adviser view digest: {self.view_digest}",
        ]
        if self.rejected:
            head.append(f"Engine check: LLM answer rejected ({', '.join(self.rejected)})")
        lines = [*head, ""]
        for title, body in self.sections():
            lines.append(title)
            lines.extend(f"  {b}" for b in body)
        lines.append(f"Context ({CONTEXT_LABEL}):")
        if not self.context:
            lines.append("  none")
        for c in self.context:
            lines.append(f"  {c.source_file} p.{c.page} [{c.label}]")
            lines.append(f"    {c.text[:300]}{'...' if len(c.text) > 300 else ''}")
        return "\n".join(lines)


def view_digest(view: RoleView) -> str:
    text = json.dumps(canonical_view(view), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def availability_note(view: RoleView) -> str:
    facts = ", ".join(f.id for f in view.facts) or "none"
    return (
        f"Facts in the adviser's view at T+{view.minute:02d}: {facts}. A fact released later, "
        "held by a role that has not shared it, or outside the adviser's boundary is not "
        "available to the adviser at this step; that does not mean it does not exist."
    )


def _label_uncertainty(items: Sequence[EvidenceItem]) -> list[str]:
    notes: list[str] = []
    for e in items:
        label = e.status_label
        if e.illustrative:
            notes.append(f"{e.clause_id} is an illustrative scenario rule, not a source clause.")
        if "binding unknown" in label:
            notes.append(f"{e.clause_id}: whether it binds is unknown (binding unknown).")
        if "(interpreted)" in label:
            notes.append(f"{e.clause_id}: the engine's reading of it is an interpretation.")
        if "English translation" in label:
            notes.append(f"{e.clause_id}: an English text; the Arabic text is authoritative.")
        if "web transcription" in label:
            notes.append(f"{e.clause_id}: quoted from a web transcription.")
    return notes


def _responsible(items: Sequence[EvidenceItem], role_ids: frozenset[str]) -> str:
    """The roles named as actor by the engine's reading of the cited UAE clauses, or
    NOT_ESTABLISHED. The reading is the engine's, not a legal conclusion."""
    named: dict[str, list[str]] = {}
    for e in items:
        actor = e.reading.split(": ", 1)[1].split(" ", 1)[0] if ": " in e.reading else ""
        if actor in role_ids:
            named.setdefault(actor, []).append(e.clause_id)
    if not named:
        return NOT_ESTABLISHED
    labels = {e.clause_id: e.status_label for e in items}
    roles = "; ".join(
        f"{role} ({', '.join(f'{i} [{labels[i]}]' for i in ids)})" for role, ids in named.items()
    )
    return (
        f"{roles}: the actor in the engine's reading of each cited clause (see section 6). "
        "Whether a reading answers this question is for a human expert."
    )


def _options(items: Sequence[EvidenceItem], view: RoleView) -> list[str]:
    lines = [
        f"{kind.capitalize()} ({e.clause_id} [{e.status_label}]; engine reading): "
        f"{e.reading.split(': ', 1)[1]}"
        for e in items
        for kind in ("permission", "prohibition", "obligation", "safeguard")
        if e.reading.startswith(f"{kind}: ")
    ]
    lines.append(f"The adviser itself may: {', '.join(view.allowed_actions)}.")
    return lines


def template_answer(
    scenario_id: str,
    question: str,
    view: RoleView,
    retrieved: Retrieved,
    role_ids: frozenset[str],
    mode_detail: str,
    rejected: AnswerCheck | None = None,
) -> AdviserAnswer:
    uae = tuple(e for e in retrieved.candidates if e.uae)[:MAX_UAE]
    international = tuple(e for e in retrieved.candidates if not e.uae)[:MAX_INTERNATIONAL]
    cited = (*uae, *international)
    abstained = not cited
    if abstained:
        direct = (
            "The adviser abstains: a loaded clause supporting an answer to this question was "
            f"{NOT_IDENTIFIED} at T+{view.minute:02d}. Absence from the reviewed corpus says "
            "nothing about whether UAE law addresses the question."
        )
    else:
        named = "; ".join(f"{e.clause_id} [{e.status_label}]" for e in cited)
        direct = (
            f"Deterministic summary (no model): the loaded clauses that best match the question "
            f"are {named}. "
        )
        if not uae:
            direct += f"A UAE clause on this question was {NOT_IDENTIFIED}. "
        readings = [f"{e.clause_id}: {e.reading}" for e in uae if e.reading]
        if readings:
            direct += "The engine's readings: " + "; ".join(readings) + ". "
        direct += "This template does not interpret the clauses: read the quotes below."
    uncertainty = [
        *_label_uncertainty(cited),
        availability_note(view),
        "The template matches question words against clause text; a relevant clause that uses "
        "other words can be missed.",
    ]
    if retrieved.retrieval == RETRIEVAL_KEYWORD:
        uncertainty.append(KEYWORD_NOTE)
    return AdviserAnswer(
        scenario=scenario_id,
        question=question,
        minute=view.minute,
        view_digest=view_digest(view),
        mode=MODE_TEMPLATE,
        mode_detail=mode_detail,
        retrieval=retrieved.retrieval,
        abstained=abstained,
        direct_answer=direct,
        uae_evidence=uae,
        status_labels=tuple((e.clause_id, e.status_label) for e in cited),
        international=international,
        responsible_role=_responsible(uae, role_ids) if uae else NOT_ESTABLISHED,
        options=tuple(_options(uae, view)),
        escalation=ESCALATION + _obligation_lines(view),
        uncertainty=tuple(uncertainty),
        facts_in_view=tuple(f.id for f in view.facts),
        retrieved=tuple(e.clause_id for e in retrieved.candidates),
        context=retrieved.context,
        rejected=rejected.reasons if rejected is not None else (),
        unknown_citations=rejected.unknown_ids if rejected is not None else (),
    )


def _obligation_lines(view: RoleView) -> tuple[str, ...]:
    return tuple(
        f"Open obligation of the adviser: {o.action} ({o.source} [{o.source_label}])"
        for o in view.open_obligations
    )


# --- LLM mode ----------------------------------------------------------------------------------


class CitedClause(DomainModel):
    clause_id: str
    relevance: str


class AdviserPayload(DomainModel):
    """What the model returns. Quotes, sources, pages and labels are filled from the clauses."""

    abstain: bool
    direct_answer: str = Field(min_length=1)
    uae_evidence: tuple[CitedClause, ...]
    international_comparison: tuple[CitedClause, ...]
    responsible_role: str = Field(min_length=1)
    options: tuple[str, ...]
    escalation: tuple[str, ...]
    uncertainty: tuple[str, ...]


def payload_schema() -> dict[str, Any]:
    return _strict(AdviserPayload.model_json_schema())


SYSTEM_PROMPT = f"""\
You are the Policy and Legal Adviser in a hypothetical, synthetic incident simulation. A judge
has paused the simulation and asks you a question. Answer only from the evidence in the user
message: your own view at this step, the citable clauses listed, and the context chunks.
Rules:
- Cite only clause ids from "citable_clauses". Put UAE clauses (uae: true) under uae_evidence
  and the others under international_comparison; never mix them.
- Context chunks are "{CONTEXT_LABEL}": never cite them.
- Do not quote: the simulation shows each clause's verbatim text, source, page and status.
- Distinguish binding UAE law from non-binding guidance and foreign or international precedent,
  using each clause's status label.
- If no listed clause supports an answer, set abstain to true, cite nothing, list no options,
  and say the answer is {NOT_IDENTIFIED}.
- Never say that anything is absent, lacking, missing, unclear or not required, or that a gap
  exists: say only what the listed clauses state.
- Never state a clause's status or whether it binds (no "binding", "mandatory", "federal law"):
  the simulation shows each clause's status label next to it.
- Never authorise, approve, permit, waive or override anything: you advise only.
- responsible_role: a role id from "known_roles" followed by a short reason drawn from a cited
  clause, or exactly "{NOT_ESTABLISHED}".
- Use only facts in "facts_in_your_view". A fact not listed is not available to you at this step;
  never say it does not exist.
- You advise; you have no enforcement authority. Say which human decision-maker must decide.
- State your uncertainty.
"""


def system_prompt(output_mode: str) -> str:
    if output_mode == "json_schema":
        return SYSTEM_PROMPT
    schema = json.dumps(payload_schema(), ensure_ascii=False, sort_keys=True)
    return (
        f"{SYSTEM_PROMPT}The reply must be one JSON object, with no other text, that validates "
        f"against this JSON schema:\n{schema}\n"
    )


def user_message(
    question: str,
    view: RoleView,
    offered: Sequence[EvidenceItem],
    context: Sequence[ContextItem],
    role_ids: Sequence[str],
) -> str:
    data = {
        "question": question,
        "role_id": view.role_id,
        "minute": view.minute,
        "simulation_time": view.at.isoformat(),
        "instructions": view.instructions,
        "facts_in_your_view": [
            {"id": f.id, "statement": f.statement, "certainty": f.certainty.value}
            for f in view.facts
        ],
        "your_open_obligations": [
            {"action": o.action, "source": o.source, "status": o.status}
            for o in view.open_obligations
        ],
        "known_roles": list(role_ids),
        "citable_clauses": [
            {
                "id": e.clause_id,
                "title": e.title,
                "status": e.status_label,
                "uae": e.uae,
                "text": e.quote,
                "engine_reading": e.reading,
            }
            for e in offered
        ],
        "context": {
            "label": CONTEXT_LABEL,
            "chunks": [
                {"source_file": c.source_file, "page": c.page, "label": c.label, "text": c.text}
                for c in context
            ],
        },
    }
    return json.dumps(data, ensure_ascii=False, indent=1)


def build_request(
    model: str,
    question: str,
    view: RoleView,
    offered: Sequence[EvidenceItem],
    context: Sequence[ContextItem],
    role_ids: Sequence[str],
    output_mode: str,
) -> dict[str, Any]:
    response_format: dict[str, Any] = (
        {
            "type": "json_schema",
            "json_schema": {"name": "adviser_answer", "strict": True, "schema": payload_schema()},
        }
        if output_mode == "json_schema"
        else {"type": "json_object"}
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt(output_mode)},
            {"role": "user", "content": user_message(question, view, offered, context, role_ids)},
        ],
        "temperature": 0,
        "response_format": response_format,
        "extra_body": {
            "provider": {"require_parameters": True},
            "reasoning": {"enabled": False},
            "plugins": [{"id": "response-healing", "enabled": False}],
        },
    }


def answer_key(request: dict[str, Any], view: RoleView) -> str:
    """Cache key: the whole request (prompt version, model id, question, view, offered clauses
    and context) and the adviser's view. The model id is hashed, never written out."""
    payload = {"prompt_version": PROMPT_VERSION, "request": request, "view": canonical_view(view)}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AnswerCache:
    """One JSON file per key: the model's validated payload and usage, never the request."""

    def __init__(self, directory: Path = DEFAULT_ANSWER_CACHE) -> None:
        self.directory = directory

    def get(self, key: str) -> AdviserPayload | None:
        path = self.directory / f"{key}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("key") != key or data.get("prompt_version") != PROMPT_VERSION:
                return None
            return AdviserPayload.model_validate(data["payload"])
        except (OSError, ValueError, KeyError, TypeError, ValidationError):
            return None

    def put(self, key: str, payload: AdviserPayload, usage: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        data = {
            "key": key,
            "prompt_version": PROMPT_VERSION,
            "payload": payload.model_dump(mode="json"),
            "usage": usage,
        }
        path = self.directory / f"{key}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def _parse(content: str | None) -> AdviserPayload | None:
    if content is None:
        return None
    try:
        return AdviserPayload.model_validate_json(content)
    except (ValidationError, ValueError):
        return None


def llm_answer(
    payload: AdviserPayload,
    scenario_id: str,
    question: str,
    view: RoleView,
    retrieved: Retrieved,
    offered: Sequence[EvidenceItem],
    clauses: Mapping[str, PolicyClause],
    role_ids: frozenset[str],
    mode_detail: str,
    usage: dict[str, Any],
) -> AdviserAnswer:
    """The model's answer if the engine accepts it, else the template with the reasons."""
    by_id = {e.clause_id: e for e in offered}
    citable = {cid: clauses[cid] for cid in by_id}
    check = check_answer(
        abstain=payload.abstain,
        uae_ids=[c.clause_id for c in payload.uae_evidence],
        international_ids=[c.clause_id for c in payload.international_comparison],
        direct_answer=payload.direct_answer,
        free_text=[
            *payload.escalation,
            *payload.uncertainty,
            *(c.relevance for c in (*payload.uae_evidence, *payload.international_comparison)),
        ],
        options=payload.options,
        responsible_role=payload.responsible_role,
        citable=citable,
        role_ids=role_ids,
    )
    if not check.ok:
        detail = TEMPLATE_REJECTED.format(reasons=", ".join(check.reasons))
        return template_answer(scenario_id, question, view, retrieved, role_ids, detail, check)
    if payload.abstain:  # the model's words are dropped: the engine's abstention is shown
        empty = Retrieved((), retrieved.context, retrieved.retrieval)
        shown = template_answer(scenario_id, question, view, empty, role_ids, LLM_ABSTAINED)
        return replace(
            shown, mode=MODE_LLM, retrieved=tuple(e.clause_id for e in offered), usage=usage
        )

    def filled(cited: Sequence[CitedClause]) -> tuple[EvidenceItem, ...]:
        unique = dict.fromkeys(c.clause_id for c in cited)
        notes = {c.clause_id: agent_statement(c.relevance) for c in cited}
        return tuple(_with_note(by_id[cid], notes[cid]) for cid in unique)

    uae, international = filled(payload.uae_evidence), filled(payload.international_comparison)
    # Every line the model wrote is shown under the engine's agent-statement label, on one line.
    uncertainty = [
        *(agent_statement(u) for u in payload.uncertainty),
        *_label_uncertainty((*uae, *international)),
    ]
    uncertainty.append(availability_note(view))
    if retrieved.retrieval == RETRIEVAL_KEYWORD:
        uncertainty.append(KEYWORD_NOTE)
    return AdviserAnswer(
        scenario=scenario_id,
        question=question,
        minute=view.minute,
        view_digest=view_digest(view),
        mode=MODE_LLM,
        mode_detail=mode_detail,
        retrieval=retrieved.retrieval,
        abstained=payload.abstain,
        direct_answer=agent_statement(payload.direct_answer),
        uae_evidence=uae,
        status_labels=tuple((e.clause_id, e.status_label) for e in (*uae, *international)),
        international=international,
        responsible_role=agent_statement(payload.responsible_role),
        # The engine's readings of the cited UAE clauses first; the model's suggestions are
        # labelled agent statements, never permissions.
        options=(
            *_options(uae, view),
            *(agent_statement(f"{SUGGESTION}{o}") for o in payload.options),
        ),
        escalation=(
            *ESCALATION,
            *(agent_statement(e) for e in payload.escalation),
            *_obligation_lines(view),
        ),
        uncertainty=tuple(uncertainty),
        facts_in_view=tuple(f.id for f in view.facts),
        retrieved=tuple(e.clause_id for e in retrieved.candidates),
        context=retrieved.context,
        usage=usage,
    )


def _with_note(e: EvidenceItem, note: str) -> EvidenceItem:
    return replace(e, relevance=note)


# --- Entry point -------------------------------------------------------------------------------


@dataclass
class Asker:
    """How a question is answered: which embedder and chat client, if any, and the cache.

    `config` None: no key (template mode, keyword or stored-vector retrieval). `offline`: the
    cache only, no call. `client`: a chat client (built from `config` by the CLI; a fake in
    tests). `embedder`: live query embeddings for free text (None: keyword half only)."""

    config: LLMConfig | None = None
    offline: bool = False
    client: Any = None
    embedder: kb.Embedder | None = None
    cache: AnswerCache = field(default_factory=AnswerCache)
    model: str | None = None  # offline: the model id from .env, to find cached answers
    output_mode: str = "json_schema"
    stored: kb.Embedder | None = None  # preset question vectors
    index: kb.Index | None = None
    template_detail: str = TEMPLATE_NO_KEY  # the mode shown when no model is configured


def failure_reason(exc: BaseException) -> str:
    """A short, fixed description of a failed live call: never the error's own text."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status == 429 or name == "DailyLimitReached":
        return "rate limit (HTTP 429)"
    if "Timeout" in name:
        return "timeout"
    if name == "CapReached":
        return "request cap reached"
    if isinstance(status, int):
        return f"HTTP {status}"
    return "error"


def clean_question(text: str) -> str:
    """The question on one line, control and format characters (escape sequences, zero-width
    marks) replaced by spaces, so it cannot forge an output line."""
    visible = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in text)
    return " ".join(visible.split())


def load_presets(scenario_dir: Path) -> tuple[tuple[int, str], ...]:
    path = scenario_dir / PRESETS_FILE
    if not path.is_file():
        return ()
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = cast(list[dict[str, Any]], data["questions"])
    return tuple((int(q["at"]), " ".join(str(q["text"]).split())) for q in questions)


def ask(
    scenario_id: str,
    question: str,
    view: RoleView,
    clauses: Mapping[str, PolicyClause],
    role_ids: Sequence[str],
    asker: Asker,
    presets: Sequence[str] = (),
) -> AdviserAnswer:
    """Answer one question at the step of `view` (the adviser's own view)."""
    if view.role_id != ADVISER:
        raise ValueError(f"the question goes to {ADVISER}, not {view.role_id}")
    question = clean_question(question)
    if not question:
        raise ValueError("the question is empty")
    roles = frozenset(role_ids)
    vectors = QueryVectorCache(asker.cache.directory)
    embedder: kb.Embedder | None
    if question in presets and asker.stored is not None:
        embedder, retrieval = asker.stored, RETRIEVAL_STORED
    elif vectors.has(question):
        embedder, retrieval = vectors, RETRIEVAL_CACHED
    elif asker.embedder is not None and not asker.offline:
        embedder, retrieval = vectors.recording(asker.embedder), RETRIEVAL_LIVE
    else:
        embedder, retrieval = None, RETRIEVAL_KEYWORD
    try:
        context = retrieve_context(question, view, embedder, asker.index)
    except Exception as exc:  # the live query embedding failed: the no-key answer, labelled
        if retrieval != RETRIEVAL_LIVE:
            raise
        context = retrieve_context(question, view, None, asker.index)
        retrieved = Retrieved(
            rank_clauses(question, view, clauses, context), context, RETRIEVAL_KEYWORD
        )
        detail = TEMPLATE_FAILED.format(reason=f"query embedding, {failure_reason(exc)}")
        return template_answer(scenario_id, question, view, retrieved, roles, detail)
    candidates = rank_clauses(question, view, clauses, context)
    retrieved = Retrieved(candidates, context, retrieval)
    model = asker.config.model if asker.config is not None else asker.model
    if model is None:
        return template_answer(scenario_id, question, view, retrieved, roles, asker.template_detail)
    offered = candidates[:LLM_CANDIDATES]
    request = build_request(
        model, question, view, offered, context, sorted(roles), asker.output_mode
    )
    key = answer_key(request, view)
    cached = asker.cache.get(key)
    if cached is not None:
        return llm_answer(
            cached, scenario_id, question, view, retrieved, offered, clauses, roles, LLM_CACHED, {}
        )
    if asker.offline or asker.client is None:
        detail = TEMPLATE_OFFLINE if asker.offline else TEMPLATE_NO_CLIENT
        return template_answer(scenario_id, question, view, retrieved, roles, detail)
    payload: AdviserPayload | None = None
    usage: dict[str, Any] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
    problem = "invalid output twice"
    for _ in range(ATTEMPTS):
        usage["calls"] += 1
        try:
            response = asker.client.chat.completions.create(**request)
        except Exception as exc:  # after the client's own retries: timeout, 429, cap, any error
            problem = failure_reason(exc)
            break
        u = getattr(response, "usage", None)
        usage["prompt_tokens"] += int(getattr(u, "prompt_tokens", 0) or 0)
        usage["completion_tokens"] += int(getattr(u, "completion_tokens", 0) or 0)
        payload = _parse(_content(response))
        if payload is not None:
            break
    if payload is None:
        detail = TEMPLATE_FAILED.format(reason=problem)
        return template_answer(scenario_id, question, view, retrieved, roles, detail)
    asker.cache.put(key, payload, usage)
    return llm_answer(
        payload, scenario_id, question, view, retrieved, offered, clauses, roles, LLM_LIVE, usage
    )


def _env(names: Sequence[str], env_file: Path | None) -> dict[str, str]:
    path = llm.ENV_FILE if env_file is None else env_file  # read at call time (tests patch it)
    values = {k: v for k, v in dotenv_values(path).items() if k in names and v and v.strip()}
    values |= {k: os.environ[k] for k in names if os.environ.get(k, "").strip()}
    return values


def api_key_is_set(env_file: Path | None = None) -> bool:
    """OPENROUTER_API_KEY is set (.env or the environment): the UI shows its live switch."""
    return bool(_env(("OPENROUTER_API_KEY",), env_file))


def key_is_set(env_file: Path | None = None) -> bool:
    """Every LLM variable is set (.env or the environment): LLM mode. Else template mode."""
    return len(_env(llm.ENV_VARIABLES, env_file)) == len(llm.ENV_VARIABLES)


def no_model_detail(env_file: Path | None = None) -> str:
    """The template's mode text when LLM mode is off: a key without CASCADEGUARD_MODEL says
    so (AGENTS.md: never a default model), anything else is "no API key"."""
    keyed = bool(_env(("OPENROUTER_API_KEY",), env_file))
    return TEMPLATE_NO_MODEL if keyed and model_or_none(env_file) is None else TEMPLATE_NO_KEY


def model_or_none(env_file: Path | None = None) -> str | None:
    """CASCADEGUARD_MODEL alone (offline replay needs no key), or None."""
    return _env(("CASCADEGUARD_MODEL",), env_file).get("CASCADEGUARD_MODEL", "").strip() or None


class QueryVectorCache:
    """Query vectors embedded live for free-text questions, kept beside the answers so an
    offline replay retrieves the same context. Each file records the model slug; a vector from
    any other model is refused (only the manifest's model is ever used)."""

    def __init__(self, answers_dir: Path) -> None:
        self.directory = answers_dir / "query_vectors"
        self._inner: kb.Embedder | None = None

    def _path(self, text: str) -> Path:
        return self.directory / f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}.json"

    def _read(self, text: str) -> kb.Vectors | None:
        try:
            data = json.loads(self._path(text).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        if data.get("model_slug") != kb.MODEL_SLUG or data.get("query") != text:  # pyright: ignore[reportUnknownMemberType]
            return None
        try:
            vector = np.array(data["vector"], dtype=np.float32)[None, :]  # pyright: ignore[reportUnknownArgumentType]
            kb.usable(vector)
        except (KeyError, TypeError, ValueError, kb.KnowledgeBaseError):
            return None
        return vector if vector.shape == (1, kb.DIMENSIONS) else None

    def has(self, text: str) -> bool:
        return self._read(text) is not None

    def recording(self, inner: kb.Embedder) -> "QueryVectorCache":
        self._inner = inner
        return self

    def documents(self, texts: Sequence[str]) -> kb.Vectors:
        raise kb.KnowledgeBaseError("the query vector cache embeds no documents")

    def query(self, text: str) -> kb.Vectors:
        found = self._read(text)
        if found is not None:
            return found
        if self._inner is None:
            raise kb.KnowledgeBaseError("no cached vector for this question")
        vector = self._inner.query(text)
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {
            "model_slug": kb.MODEL_SLUG,
            "query": text,
            "vector": [float(x) for x in vector[0]],
        }
        self._path(text).write_text(json.dumps(record), encoding="utf-8")
        return vector
